import cv2
import numpy as np
import time
import vgamepad as vg
from win32api import GetSystemMetrics
from collections import deque
import mediapipe.python.solutions.hands as mp_hands

# ============================================================
#  RACING HAND CONTROLLER
#
#  POSIÇÃO DE DIRIGIR:
#   - Mãos FECHADAS (punho) = posição neutra de direção
#   - Polegar para CIMA  (mão dir, punho) → Subir marcha  [B]
#   - Polegar para BAIXO (mão dir, punho) → Descer marcha [X]
#   - Sequência de marchas: R → 1 → 2 → 3 → 4 → 5 → 6
#
#  ACELERAR / FREAR:
#   - Ambas as mãos acima linha verde  → RT Acelerar
#   - Ambas as mãos abaixo linha vermelha → LT Frear
#
#  VOLANTE:
#   - Diferença de altura entre mãos → Joystick analógico
#   - Freeze de 0.35s após troca de marcha (evita virar ao trocar)
#   - Confirmação em 3 frames para gesto de marcha (evita falsos)
#
#  TECLAS DO PROGRAMA:
#   - 'x'   → Sair
#   - 'c'   → Recalibrar EMA
#   - 'm'   → Modo calibração (descobre CURVA_MAXIMA ideal)
#   - 'r'   → Resetar marcha para 1ª
#   - '+'/'-' → Ajustar marcha manualmente (ressincronizar com jogo)
#
#  COMO CALIBRAR O VOLANTE:
#   1. Pressione 'm' para entrar no modo calibração
#   2. Incline as mãos para o lado direito no máximo confortável
#   3. Incline para o lado esquerdo no máximo confortável
#   4. Anote o valor "max_visto" que aparece no HUD
#   5. Pressione 'm' para sair
#   6. Edite CURVA_MAXIMA abaixo com o valor anotado
#
#  COMO AJUSTAR EMA (suavização):
#   - EMA_ALPHA_VOLANTE: 0.22 padrão
#     → Aumentar (ex: 0.35) = mais responsivo, pode tremer
#     → Diminuir (ex: 0.12) = mais suave, pequeno atraso
#   - EMA_ALPHA_GATILHO: 0.32 padrão (acelerar/frear)
#     → Geralmente não precisa ajustar
# ============================================================

gamepad = vg.VX360Gamepad()

# --- JANELA ---
width  = int(GetSystemMetrics(0))
height = int(GetSystemMetrics(1))
scale_percent = 0.35
dsize   = (int(width * scale_percent), int(height * scale_percent))
winname = "Racing Controller v4.2"
cv2.namedWindow(winname)
cv2.moveWindow(winname, int(width * 0.65), 0)

# ------------------------------------------------------------------ #
#  CONFIGURAÇÕES — edite aqui
# ------------------------------------------------------------------ #

# --- Volante ---
LINHA_VERDE    = 0.40   # Y acima desta linha = zona de aceleração
LINHA_VERMELHA = 0.60   # Y abaixo desta linha = zona de freio
DEADZONE_CURVA = 0.05   # zona morta central do volante (aumentada: menos deriva)
CURVA_MAXIMA   = 0.22   # inclinação máxima → 100% do volante (calibre com 'm')
EXPOENTE_CURVA = 0.7    # curva de resposta: 0.5=agressivo, 1.0=linear

# --- EMA (suavização) ---
# Quanto MAIOR o alpha, MAIS RESPONSIVO (menos suave)
# Quanto MENOR o alpha, MAIS SUAVE (pequeno atraso)
EMA_ALPHA_VOLANTE = 0.22   # volante: suave para curvas fluidas
EMA_ALPHA_GATILHO = 0.32   # gatilhos: mais rápido para acelerar/frear

# --- Câmbio ---
MARCHA_MIN            = -1    # -1 = Ré
MARCHA_MAX            =  6    # máximo 6ª
DEBOUNCE_MARCHA       = 0.7   # segundos mínimos entre trocas
FREEZE_VOLANTE_SHIFT  = 0.35  # segundos que o volante fica parado após troca
FRAMES_CONFIRMACAO    = 3     # frames consecutivos para confirmar gesto de marcha
MARGEM_POLEGAR        = 0.07  # margem de direção do polegar (cima/baixo)
# NOVO: distância mínima do tip do polegar ao MCP do indicador
# No punho fechado → distância pequena (<0.14) = NEUTRO, sem troca
# No joinha real   → distância grande (>0.14) = polegar estendido de fato
DIST_POLEGAR_ESTENDIDO = 0.14

# --- Câmera ---
TARGET_FPS = 30

# ------------------------------------------------------------------ #

# Estado EMA
ema_y_esq    = 0.0
ema_y_dir    = 0.0
ema_dist     = 0.0
primeiro_frame = True

# Estado de câmbio
marcha_atual        = 1
ultimo_shift        = 0.0
seta_marcha         = ""
seta_timer          = 0.0
freeze_volante_ate  = 0.0
buf_gesto_dir       = deque(maxlen=FRAMES_CONFIRMACAO)

# Máquina de estados do polegar:
# Só aciona marcha quando polegar VEM DO NEUTRO (punho fechado)
# Impede que punho naturalmente alto dispare marchas em loop
polegar_em_neutro = True   # começa True para permitir a 1ª troca

# Modo calibração
modo_calibracao = False
dist_max_visto  = 0.0

# Câmera
camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
camera.set(cv2.CAP_PROP_FRAME_WIDTH,  1920)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
camera.set(cv2.CAP_PROP_FPS, TARGET_FPS)

print("[INFO] Racing Controller v4.2 iniciado!")
print("  Punhos fechados                    → posição de dirigir")
print("  Polegar DIR p/ cima (punho)        → Subir marcha  [B]")
print("  Polegar DIR p/ baixo (punho)       → Descer marcha [X]")
print("  Marchas: R → 1 → 2 → 3 → 4 → 5 → 6")
print("  'x'=sair | 'c'=EMA | 'm'=calibrar | 'r'=reset marcha | +/-=ajuste")
print("-" * 60)


# ------------------------------------------------------------------ #
#  HELPERS
# ------------------------------------------------------------------ #
def label_marcha(m):
    if m == -1: return "R"
    return str(m)


PARES_3D     = [(5,8), (9,12), (13,16), (17,20)]
DIST_DOBRADO = 0.12

def estado_mao(lm):
    """Retorna 'ABERTA', 'FECHADA' ou 'PARCIAL' via distância 3D tip→MCP."""
    dobrados = 0
    wrist_x   = lm[0].x
    thumb_mcp = lm[2].x
    thumb_tip = lm[4].x
    lado = 1 if thumb_mcp > wrist_x else -1
    if (thumb_tip - thumb_mcp) * lado < 0.02:
        dobrados += 1
    for mcp_i, tip_i in PARES_3D:
        mcp = lm[mcp_i]; tip = lm[tip_i]
        dist = ((tip.x-mcp.x)**2 + (tip.y-mcp.y)**2 + (tip.z-mcp.z)**2) ** 0.5
        if dist < DIST_DOBRADO:
            dobrados += 1
    if dobrados >= 4: return "FECHADA"
    if dobrados <= 1: return "ABERTA"
    return "PARCIAL"


def gesto_marcha_det(lm):
    """
    Detecta estado do polegar: 'NEUTRO', 'POLEGAR_CIMA', 'POLEGAR_BAIXO'.

    TRÊS critérios obrigatórios para CIMA ou BAIXO:
      1. ≥3 dos 4 dedos dobrados (mão em punho)
      2. Polegar ESTENDIDO: distância tip→MCP do indicador > DIST_POLEGAR_ESTENDIDO
         → No punho fechado o polegar fica junto dos dedos (dist pequena = NEUTRO)
         → No joinha real o polegar sai da mão (dist grande = estendido)
      3. Direção clara: diff Y > MARGEM_POLEGAR

    Retorna 'NEUTRO' quando punho fechado sem extensão do polegar.
    Retorna None quando mão não está em punho.
    """
    # Critério 1: punho (≥3 dedos dobrados)
    dedos_dobrados = 0
    for mcp_i, tip_i in PARES_3D:
        mcp = lm[mcp_i]; tip = lm[tip_i]
        dist = ((tip.x-mcp.x)**2 + (tip.y-mcp.y)**2 + (tip.z-mcp.z)**2) ** 0.5
        if dist < DIST_DOBRADO:
            dedos_dobrados += 1
    if dedos_dobrados < 3:
        return None   # mão não está em punho, ignora

    # Critério 2: polegar estendido (distância tip polegar → MCP indicador)
    # lm[4] = tip do polegar | lm[5] = MCP do indicador
    ext = ((lm[4].x - lm[5].x)**2 +
           (lm[4].y - lm[5].y)**2 +
           (lm[4].z - lm[5].z)**2) ** 0.5
    if ext < DIST_POLEGAR_ESTENDIDO:
        return "NEUTRO"   # polegar tucado dentro do punho → posição de dirigir

    # Critério 3: direção (cima ou baixo)
    diff = lm[2].y - lm[4].y   # positivo = tip acima do MCP
    if diff >  MARGEM_POLEGAR: return "POLEGAR_CIMA"
    if diff < -MARGEM_POLEGAR: return "POLEGAR_BAIXO"
    return "NEUTRO"   # estendido mas sem direção clara


def confirmar_gesto(buf):
    """Retorna gesto só se N frames consecutivos detectaram o mesmo."""
    if len(buf) < FRAMES_CONFIRMACAO or buf[0] is None:
        return None
    return buf[0] if all(g == buf[0] for g in buf) else None


def curva_resposta(v):
    """Curva de potência: suave no centro, total nos extremos."""
    return (1 if v >= 0 else -1) * (abs(v) ** EXPOENTE_CURVA)


def release_all():
    gamepad.right_trigger_float(value_float=0.0)
    gamepad.left_trigger_float(value_float=0.0)
    gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
    gamepad.update()


# ------------------------------------------------------------------ #
#  HUD
# ------------------------------------------------------------------ #
def desenhar_hud(img, acelerando, freando, eixo_x,
                 estado_esq, estado_dir, fps,
                 calibrando, dist_max,
                 marcha, seta, gesto_frame, volante_frozen,
                 polegar_neutro):
    h, w = img.shape[:2]

    altura = 290 if calibrando else 260
    ov = img.copy()
    cv2.rectangle(ov, (10, 10), (360, altura), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.5, img, 0.5, 0, img)

    COR = {
        "ABERTA":        (0, 255, 120),
        "FECHADA":       (0,  80, 255),
        "PARCIAL":       (0, 200, 255),
        "POLEGAR_CIMA":  (0, 255, 255),
        "POLEGAR_BAIXO": (255, 100,   0),
        None:            (80,  80,  80),
    }

    cv2.putText(img, "v4.2", (308, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (80,80,80), 1)

    # Gestos das mãos
    dir_disp = gesto_frame if gesto_frame else estado_dir
    cv2.putText(img, f"ESQ: {estado_esq or '---'}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COR.get(estado_esq, COR[None]), 2)
    cv2.putText(img, f"DIR: {dir_disp or '---'}", (20, 70),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COR.get(dir_disp, COR[None]), 2)

    # Dica: punho fechado
    if estado_esq != "FECHADA" or estado_dir not in ("FECHADA", "PARCIAL"):
        cv2.putText(img, "feche os punhos para dirigir", (20, 92),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (120, 120, 60), 1)

    # Acelerar / Frear
    cv2.putText(img, "RT ACELERAR", (20, 112),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 255, 100) if acelerando else (60, 60, 60), 2)
    cv2.putText(img, "LT FREAR", (20, 140),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 80, 255) if freando else (60, 60, 60), 2)

    # --- Marcha ---
    lbl = label_marcha(marcha)
    cor_m = (0, 80, 255) if lbl == "R" else (0, 255, 255)
    cv2.putText(img, "MARCHA", (20, 172),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
    cv2.putText(img, lbl, (108, 182),
                cv2.FONT_HERSHEY_SIMPLEX, 1.7, cor_m, 3)

    if seta == "+":
        cv2.putText(img, "SUBIU [B]",  (162, 174),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 100), 2)
    elif seta == "-":
        cv2.putText(img, "DESCEU [X]", (162, 174),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 100, 255), 2)

    if volante_frozen:
        cv2.putText(img, "VOL PAUSADO", (162, 194),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 200, 0), 1)

    # Estado da máquina de polegar
    # Verde = pronto para troca | Laranja = aguardando neutro
    cor_estado_pol = (0, 220, 80) if polegar_neutro else (0, 140, 255)
    txt_estado_pol = "PRONTO" if polegar_neutro else "FECHE O PUNHO"
    cv2.putText(img, f"SHIFT: {txt_estado_pol}", (20, 197),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, cor_estado_pol, 1)

    # --- Barra do volante ---
    bw, bx, by = 200, 20, 205
    cv2.rectangle(img, (bx, by), (bx+bw, by+15), (60,60,60), -1)
    cx = bx + bw//2
    fill = int(eixo_x * (bw//2))
    if fill:
        x0, x1 = min(cx, cx+fill), max(cx, cx+fill)
        cor_v = (80, 80, 80) if volante_frozen else (0, 200, 255)
        cv2.rectangle(img, (x0, by), (x1, by+15), cor_v, -1)
    cv2.line(img, (cx, by-2), (cx, by+17), (255,255,255), 1)
    cv2.putText(img, f"VOLANTE: {int(eixo_x*100):+d}%",
                (20, 238), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200,200,200), 1)

    # --- Calibração ---
    if calibrando:
        cv2.putText(img,
            f"[CALIB] atual={CURVA_MAXIMA:.2f}   max_visto={dist_max:.3f}",
            (20, 256), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0,255,255), 1)
        cv2.putText(img,
            f"  Incline ao max → anote max_visto → edite CURVA_MAXIMA",
            (20, 274), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0,200,200), 1)

    # FPS
    cv2.putText(img, f"FPS:{fps:.0f}", (w-100, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180,180,180), 1)

    return img


# ------------------------------------------------------------------ #
#  LOOP PRINCIPAL
# ------------------------------------------------------------------ #
with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5) as hands:

    fps_buf = deque(maxlen=30)

    while True:
        t0 = time.time()

        ret, image = camera.read()
        if not ret:
            continue

        image = cv2.flip(image, 1)
        h_img, w_img, _ = image.shape
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = hands.process(rgb)

        # Linhas de zona
        y_v = int(h_img * LINHA_VERDE)
        y_r = int(h_img * LINHA_VERMELHA)
        cv2.line(image, (0, y_v), (w_img, y_v), (0,255,0), 2)
        cv2.line(image, (0, y_r), (w_img, y_r), (0,0,255), 2)
        cv2.putText(image, "ACELERAR", (w_img-165, y_v-8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,255,0), 1)
        cv2.putText(image, "FREAR", (w_img-115, y_r+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,80,255), 1)

        # Reset por frame
        y_esq_raw = y_dir_raw = None
        pt_esq = pt_dir = None
        estado_esq = estado_dir = None
        acelerando = freando = False
        eixo_x_final = 0.0
        gesto_dir_frame = None

        agora = time.time()
        volante_frozen = agora < freeze_volante_ate

        if results.multi_hand_landmarks and results.multi_handedness:
            for idx, handedness in enumerate(results.multi_handedness):
                # label "Right" → mão ESQUERDA real (imagem espelhada)
                # label "Left"  → mão DIREITA real
                label = handedness.classification[0].label
                lm    = results.multi_hand_landmarks[idx].landmark

                y_raw = lm[mp_hands.HandLandmark.INDEX_FINGER_MCP].y
                x_raw = lm[mp_hands.HandLandmark.INDEX_FINGER_MCP].x
                px = int(x_raw * w_img)
                py = int(y_raw * h_img)
                gesto = estado_mao(lm)

                if label == "Right":          # → mão ESQUERDA real
                    y_esq_raw  = y_raw
                    pt_esq     = (px, py)
                    estado_esq = gesto
                    cor = (0,255,120) if gesto=="ABERTA" else \
                          (0,80,255) if gesto=="FECHADA" else (0,200,255)
                    cv2.circle(image, (px,py), 12, cor, -1)
                    cv2.putText(image, f"ESQ {gesto}", (px+14,py-6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 1)

                elif label == "Left":         # → mão DIREITA real
                    y_dir_raw  = y_raw
                    pt_dir     = (px, py)
                    estado_dir = gesto

                    # Detecta estado do polegar (inclui NEUTRO agora)
                    gesto_dir_frame = gesto_marcha_det(lm)

                    # --- Máquina de estados do polegar ---
                    # NEUTRO: polegar tucado no punho (posição de dirigir)
                    # Só alimenta o buffer de confirmação se VEM DO NEUTRO
                    if gesto_dir_frame == "NEUTRO":
                        polegar_em_neutro = True
                        buf_gesto_dir.append(None)   # NEUTRO não aciona nada
                    elif gesto_dir_frame in ("POLEGAR_CIMA", "POLEGAR_BAIXO"):
                        if polegar_em_neutro:
                            buf_gesto_dir.append(gesto_dir_frame)
                        else:
                            buf_gesto_dir.append(None)  # bloqueia até ver NEUTRO
                    else:
                        buf_gesto_dir.append(None)   # mão não em punho

                    cor_dir = (0,255,255) if gesto_dir_frame=="POLEGAR_CIMA"  else \
                              (255,100,0) if gesto_dir_frame=="POLEGAR_BAIXO" else \
                              (0,255,120) if gesto=="ABERTA"  else \
                              (0,80,255)  if gesto=="FECHADA" else (0,200,255)
                    cv2.circle(image, (px,py), 12, cor_dir, -1)
                    lbl_dir = gesto_dir_frame if gesto_dir_frame else gesto
                    cv2.putText(image, f"DIR {lbl_dir}", (px+14,py-6),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor_dir, 1)

            # -------------------------------------------------------- #
            #  CÂMBIO — confirma em N frames antes de acionar
            # -------------------------------------------------------- #
            gesto_conf = confirmar_gesto(buf_gesto_dir)

            if gesto_conf and (agora - ultimo_shift) >= DEBOUNCE_MARCHA:
                if gesto_conf == "POLEGAR_CIMA" and marcha_atual < MARCHA_MAX:
                    marcha_atual += 1
                    gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                    gamepad.update(); time.sleep(0.06)
                    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_B)
                    gamepad.update()
                    ultimo_shift = agora; seta_marcha = "+"; seta_timer = agora
                    freeze_volante_ate = agora + FREEZE_VOLANTE_SHIFT
                    buf_gesto_dir.clear()
                    polegar_em_neutro = False   # exige voltar ao neutro antes da próxima
                    print(f"[MARCHA] Subiu → {label_marcha(marcha_atual)}  [B]")

                elif gesto_conf == "POLEGAR_BAIXO" and marcha_atual > MARCHA_MIN:
                    marcha_atual -= 1
                    gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
                    gamepad.update(); time.sleep(0.06)
                    gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_X)
                    gamepad.update()
                    ultimo_shift = agora; seta_marcha = "-"; seta_timer = agora
                    freeze_volante_ate = agora + FREEZE_VOLANTE_SHIFT
                    buf_gesto_dir.clear()
                    polegar_em_neutro = False   # exige voltar ao neutro antes da próxima
                    print(f"[MARCHA] Desceu → {label_marcha(marcha_atual)}  [X]")

            if seta_marcha and (agora - seta_timer) > 0.6:
                seta_marcha = ""

            # -------------------------------------------------------- #
            #  GATILHOS E VOLANTE — ambas as mãos detectadas
            # -------------------------------------------------------- #
            if y_esq_raw is not None and y_dir_raw is not None:

                # EMA
                if primeiro_frame:
                    ema_y_esq = y_esq_raw
                    ema_y_dir = y_dir_raw
                    ema_dist  = y_esq_raw - y_dir_raw
                    primeiro_frame = False
                else:
                    ema_y_esq = EMA_ALPHA_GATILHO*y_esq_raw + (1-EMA_ALPHA_GATILHO)*ema_y_esq
                    ema_y_dir = EMA_ALPHA_GATILHO*y_dir_raw + (1-EMA_ALPHA_GATILHO)*ema_y_dir
                    ema_dist  = EMA_ALPHA_VOLANTE*(y_esq_raw-y_dir_raw) + (1-EMA_ALPHA_VOLANTE)*ema_dist

                if pt_esq and pt_dir:
                    cv2.line(image, pt_esq, pt_dir, (0,255,255), 3)

                # Gatilhos
                if ema_y_esq < LINHA_VERDE and ema_y_dir < LINHA_VERDE:
                    gamepad.right_trigger_float(value_float=1.0)
                    gamepad.left_trigger_float(value_float=0.0)
                    acelerando = True
                elif ema_y_esq > LINHA_VERMELHA and ema_y_dir > LINHA_VERMELHA:
                    gamepad.left_trigger_float(value_float=1.0)
                    gamepad.right_trigger_float(value_float=0.0)
                    freando = True
                else:
                    gamepad.right_trigger_float(value_float=0.0)
                    gamepad.left_trigger_float(value_float=0.0)

                # Volante — congelado após troca de marcha
                abs_dist = abs(ema_dist)
                if modo_calibracao and abs_dist > dist_max_visto:
                    dist_max_visto = abs_dist

                if not volante_frozen:
                    if abs_dist > DEADZONE_CURVA:
                        valor = (abs_dist - DEADZONE_CURVA) / (CURVA_MAXIMA - DEADZONE_CURVA)
                        valor = min(1.0, max(0.0, valor))
                        if ema_dist < 0: valor = -valor
                        eixo_x_final = curva_resposta(valor)
                        gamepad.left_joystick_float(
                            x_value_float=eixo_x_final, y_value_float=0.0)
                    else:
                        gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)

                gamepad.update()

            else:
                release_all()
                primeiro_frame = True

        else:
            release_all()
            primeiro_frame = True
            buf_gesto_dir.clear()
            polegar_em_neutro = True   # reseta ao perder tracking

        # HUD
        fps_buf.append(1.0 / max(time.time()-t0, 0.001))
        image = desenhar_hud(
            image, acelerando, freando, eixo_x_final,
            estado_esq, estado_dir, sum(fps_buf)/len(fps_buf),
            modo_calibracao, dist_max_visto,
            marcha_atual, seta_marcha, gesto_dir_frame, volante_frozen,
            polegar_em_neutro)

        cv2.imshow(winname, cv2.resize(image, dsize))
        cv2.setWindowProperty(winname, cv2.WND_PROP_TOPMOST, 1)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('x'):
            break
        elif key == ord('c'):
            primeiro_frame = True
            print("[INFO] EMA recalibrada!")
        elif key == ord('m'):
            modo_calibracao = not modo_calibracao
            dist_max_visto  = 0.0
            print(f"[INFO] Calibração {'ATIVADA' if modo_calibracao else 'DESATIVADA'}")
            if modo_calibracao:
                print(f"  CURVA_MAXIMA atual: {CURVA_MAXIMA}")
                print("  Incline as mãos ao máximo → anote max_visto → edite CURVA_MAXIMA")
        elif key == ord('r'):
            marcha_atual = 1; seta_marcha = ""; buf_gesto_dir.clear()
            print("[INFO] Marcha resetada → 1ª")
        elif key in (ord('+'), ord('=')):
            if marcha_atual < MARCHA_MAX:
                marcha_atual += 1
                print(f"[INFO] Marcha ajustada → {label_marcha(marcha_atual)}")
        elif key == ord('-'):
            if marcha_atual > MARCHA_MIN:
                marcha_atual -= 1
                print(f"[INFO] Marcha ajustada → {label_marcha(marcha_atual)}")

        elapsed = time.time() - t0
        sleep_t = (1.0/TARGET_FPS) - elapsed
        if sleep_t > 0: time.sleep(sleep_t)

release_all()
camera.release()
cv2.destroyAllWindows()
print("[INFO] Controller encerrado.")