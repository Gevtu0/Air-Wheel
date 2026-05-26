# AirWheel - Virtual Analog Gamepad using Computer Vision

Este projeto utiliza **Python**, **OpenCV** e **MediaPipe Hands** para transformar os movimentos das mãos capturados por uma webcam em comandos analógicos reais de um controle de Xbox 360 (via **ViGEmBus**). Otimizado especialmente para jogos de corrida como *Forza Horizon 4*.

## 🚀 Funcionalidades
- Resolução otimizada para câmera em 1080p.
- Controle de direção 100% analógico e progressivo baseado nos nós dos dedos.
- Aceleração (RT) e Frenagem (LT) através de linhas guias verticais.
- Rastreamento estável mesmo com as mãos fechadas em punho.

## 🛠️ Pré-requisitos
1. Instalar o driver do [ViGEmBus](https://github.com/nefarius/ViGEmBus/releases).
2. Ter uma webcam configurada.

## 📦 Como rodar
```bash
# Ative seu ambiente virtual e instale as dependências:
pip install opencv-python mediapipe vgamepad pywin32 numpy

# Execute o script:
python racing.py