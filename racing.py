import cv2
import numpy as np
import time
import vgamepad as vg  
from win32api import GetSystemMetrics
from collections import deque
import mediapipe.python.solutions.hands as mp_hands

gamepad = vg.VX360Gamepad()

# Configurações de exibição da janela na tela
width = int(GetSystemMetrics(0))
height = int(GetSystemMetrics(1))
scale_percent = 0.35  
dsize = (int(width * scale_percent), int(height * scale_percent))

winname = "Racing - 1080p Precision"
cv2.namedWindow(winname)
cv2.moveWindow(winname, int(width * 0.65), 0)

# --- CALIBRAÇÃO DE SENSIBILIDADE ---
LINHA_VERDE = 0.45       
LINHA_VERMELHA = 0.65     
DEADZONE_CURVA = 0.03     
CURVA_MAXIMA = 0.13       

historico_dist = deque(maxlen=2)

# --- CONFIGURAÇÃO DA CÂMERA EM FULL HD (1080p) ---
camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)   
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
camera.set(cv2.CAP_PROP_FPS, 30)

print("[INFO] Sistema de alta precisão iniciado. Modo estável ativado!")

with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,               
        model_complexity=0,            # Mantido em 0 para rodar liso em 1080p
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5) as hands:
        
    while True:
        start_time = time.time()
        
        return_value, image = camera.read()
        if not return_value: continue
            
        image = cv2.flip(image, 1)
        height_img, width_img, _ = image.shape
        results = hands.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        
        dist_suave = 0
        y_esq, y_dir = None, None
        pt_esq, pt_dir = (0, 0), (0, 0)

        # --- DESENHAR LINHAS HORIZONTAIS DE CONTROLE ---
        cv2.line(image, (0, int(height_img * LINHA_VERDE)), (width_img, int(height_img * LINHA_VERDE)), (0, 255, 0), 3)
        cv2.line(image, (0, int(height_img * LINHA_VERMELHA)), (width_img, int(height_img * LINHA_VERMELHA)), (0, 0, 255), 3)

        if results.multi_hand_landmarks and results.multi_handedness:
            try:
                for idx, hand_handedness in enumerate(results.multi_handedness):
                    lado_da_mao = hand_handedness.classification[0].label
                    landmarks = results.multi_hand_landmarks[idx].landmark
                    
                    # Usando a base do dedo indicador (Ponto 5) para guiar o volante virtual
                    y_base_dedo = landmarks[mp_hands.HandLandmark.INDEX_FINGER_MCP].y
                    x_base_dedo = landmarks[mp_hands.HandLandmark.INDEX_FINGER_MCP].x
                    
                    # Converte para pixels para desenhar as guias na janela
                    px = int(x_base_dedo * width_img)
                    py = int(y_base_dedo * height_img)

                    # CORREÇÃO DE ESPELHAMENTO DOS LADOS
                    if lado_da_mao == "Left":
                        y_dir = y_base_dedo
                        pt_dir = (px, py)
                    elif lado_da_mao == "Right":
                        y_esq = y_base_dedo
                        pt_esq = (px, py)

                # Se as duas mãos estiverem na tela, processa os comandos
                if y_esq is not None and y_dir is not None:
                    historico_dist.append(y_esq - y_dir)
                    dist_suave = sum(historico_dist) / len(historico_dist)

                    # Desenha a linha amarela unindo as duas mãos
                    cv2.line(image, pt_esq, pt_dir, (0, 255, 255), 4)
                    cv2.circle(image, pt_esq, 8, (255, 0, 0), -1)
                    cv2.circle(image, pt_dir, 8, (255, 0, 0), -1)

                    # --- GATILHOS (RT / LT) ---
                    if y_dir < LINHA_VERDE and y_esq < LINHA_VERDE:
                        gamepad.right_trigger_float(value_float=1.0)
                        gamepad.left_trigger_float(value_float=0.0)
                    elif y_dir > LINHA_VERMELHA and y_esq > LINHA_VERMELHA:
                        gamepad.left_trigger_float(value_float=1.0)
                        gamepad.right_trigger_float(value_float=0.0)
                    else:
                        gamepad.right_trigger_float(value_float=0.0)
                        gamepad.left_trigger_float(value_float=0.0)
                            
                    # --- VOLANTE ANALÓGICO ---
                    abs_dist = abs(dist_suave)
                    if abs_dist > DEADZONE_CURVA:
                        valor_analogico = (abs_dist - DEADZONE_CURVA) / (CURVA_MAXIMA - DEADZONE_CURVA)
                        valor_analogico = min(1.0, max(0.0, valor_analogico))
                        if dist_suave < 0: valor_analogico = -valor_analogico
                        gamepad.left_joystick_float(x_value_float=valor_analogico, y_value_float=0.0)
                    else:
                        gamepad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)

                    gamepad.update()

            except Exception:
                pass

        # Telemetria simples na tela
        cv2.putText(image, f"Eixo X: {int(dist_suave * 100)}", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        image_resized = cv2.resize(image, dsize)        
        cv2.imshow(winname, image_resized)
        cv2.setWindowProperty(winname, cv2.WND_PROP_TOPMOST, 1)

        if cv2.waitKey(1) & 0xFF == ord('x'): break

    gamepad.reset()
    gamepad.update()
    camera.release(); cv2.destroyAllWindows()