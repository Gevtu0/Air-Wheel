# Air Wheel

Controle virtual para jogos de corrida usando gestos das maos capturados pela webcam.

O projeto usa Python, OpenCV, MediaPipe Hands e vgamepad para transformar movimentos das maos em comandos de um controle virtual de Xbox 360 via ViGEmBus. A ideia e jogar jogos de corrida, como Forza Horizon, sem volante fisico: as maos controlam direcao, aceleracao, freio e troca de marcha.

## Funcionalidades

- Controle analogico de direcao pela diferenca de altura entre as duas maos.
- Aceleracao no RT quando as duas maos ficam acima da linha verde.
- Freio no LT quando as duas maos ficam abaixo da linha vermelha.
- Troca de marcha pelo polegar da mao esquerda:
  - polegar para cima: sobe marcha, botao B;
  - polegar para baixo: desce marcha, botao X.
- Sequencia de marchas de R ate 6.
- Suavizacao por EMA para reduzir tremores.
- Deadzone central para evitar deriva no volante.
- Freeze rapido do volante apos troca de marcha para evitar curva acidental.
- Modo de calibracao para ajustar a sensibilidade maxima do volante.
- HUD com status das maos, marcha atual, aceleracao, freio, volante e FPS.

## Como os gestos funcionam

| Acao | Gesto |
| --- | --- |
| Dirigir | Mantenha as duas maos fechadas em punho |
| Virar | Altere a altura entre a mao esquerda e a mao direita |
| Acelerar | Coloque as duas maos acima da linha verde |
| Frear | Coloque as duas maos abaixo da linha vermelha |
| Subir marcha | Com a mao esquerda em punho, levante o polegar |
| Descer marcha | Com a mao esquerda em punho, abaixe o polegar |

## Teclas do programa

| Tecla | Funcao |
| --- | --- |
| `x` | Sair do programa |
| `c` | Recalibrar a suavizacao EMA |
| `m` | Ativar ou desativar o modo de calibracao |
| `r` | Resetar a marcha para 1a |
| `+` ou `=` | Aumentar marcha manualmente |
| `-` | Diminuir marcha manualmente |

## Pre-requisitos

- Windows.
- Webcam funcionando.
- Python instalado.
- Driver ViGEmBus instalado.
- Jogo configurado para aceitar controle de Xbox.

Instale o ViGEmBus pelo repositorio oficial:

```text
https://github.com/nefarius/ViGEmBus/releases
```

## Instalacao

Clone o repositorio:

```bash
git clone https://github.com/Gevtu0/Air-Wheel.git
cd Air-Wheel
```

Crie e ative um ambiente virtual, se quiser manter as dependencias isoladas:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Instale as dependencias:

```bash
pip install opencv-python mediapipe vgamepad pywin32 numpy
```

## Como rodar

Execute:

```bash
python racing.py
```

Ao iniciar, uma janela pequena da camera aparece no canto direito da tela. O script cria um controle virtual de Xbox 360 e envia os comandos conforme os gestos detectados.

## Calibracao do volante

O valor principal de calibracao e `CURVA_MAXIMA`, dentro do arquivo `racing.py`.

Para descobrir um valor melhor:

1. Execute o programa.
2. Pressione `m` para entrar no modo de calibracao.
3. Incline as maos para o lado direito no maximo confortavel.
4. Incline as maos para o lado esquerdo no maximo confortavel.
5. Veja o valor `max_visto` mostrado no HUD.
6. Feche o programa.
7. Edite `CURVA_MAXIMA` no codigo usando um valor proximo ao `max_visto`.

Se o volante estiver muito sensivel, aumente a deadzone ou ajuste a curva:

```python
DEADZONE_CURVA = 0.05
CURVA_MAXIMA = 0.22
EXPOENTE_CURVA = 0.7
```

## Ajustes uteis

No arquivo `racing.py`, os principais parametros sao:

```python
LINHA_VERDE = 0.40
LINHA_VERMELHA = 0.60
DEADZONE_CURVA = 0.05
CURVA_MAXIMA = 0.22
EXPOENTE_CURVA = 0.7
EMA_ALPHA_VOLANTE = 0.22
EMA_ALPHA_GATILHO = 0.32
```

- Aumentar `EMA_ALPHA_VOLANTE` deixa o volante mais responsivo, mas pode gerar tremor.
- Diminuir `EMA_ALPHA_VOLANTE` deixa o volante mais suave, mas com mais atraso.
- Aumentar `DEADZONE_CURVA` ajuda se o carro estiver virando sozinho.
- Ajustar `LINHA_VERDE` e `LINHA_VERMELHA` muda as zonas de aceleracao e freio.

## Observacoes

- O projeto depende de boa iluminacao e enquadramento das maos.
- A webcam precisa enxergar as duas maos ao mesmo tempo.
- O controle virtual aparece para o jogo como um controle de Xbox 360.
- O comportamento pode variar dependendo do jogo e das configuracoes de controle.
- O script usa recursos especificos do Windows, como `pywin32`, `vgamepad` e DirectShow.
- A imagem da camera e espelhada; por isso, a mao esquerda real pode parecer a direita na tela.

## Estrutura

```text
Air-Wheel/
|-- racing.py
|-- readme.md
`-- .gitignore
```

## Status

Projeto experimental e interativo para testar controle por gestos em jogos de corrida.
