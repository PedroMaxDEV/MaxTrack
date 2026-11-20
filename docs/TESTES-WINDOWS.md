# Aceitação Windows

## Evidência automatizada atual

- `python -m unittest discover -s tests -v`: 5 testes aprovados.
- `python tests/smoke_ui.py`: aprovado; Tcl/Tk real, webcam e atalhos simulados. Confere dois perfis e salvamento automático.
- `build/bridge/test_bridge.exe`: aprovado; SDK simulado, rede UDP real no localhost, timeout e reinicialização.
- Carregamento da DLL com ctypes e presença dos dois exports SDK: aprovado.
- Empacotamento PyInstaller com Tcl/Tk: aprovado.

## Ainda obrigatório antes de anunciar independência

1. Abrir ETS2 pela Steam. Verificar `game.log.txt` por `MaxTrack bridge` e erros de carregamento da DLL.
2. Identificar o dispositivo no menu de controles e a identificação gravada pelo jogo. Não presumir um nome de sistema de entrada.
3. Com o jogo fechado, preservar controls.sii e preparar a ligação de ativo/yaw/pitch nos mixes de head tracking. Confirmar unidades e sinais usando movimento conhecido. Não substituir controles de volante/pedais.
4. Reiniciar o jogo sem OpenTrack. Confirmar esquerda/direita, cima/baixo e posição central na cabine, com veículo parado.
5. Comparar webcam e calibração F10 com a versão original; testar F9 e perda de rosto/câmera.
6. Repetir no ATS e em máquina sem OpenTrack instalado. Guardar versões e evidências.

## Distribuição

Instalar em Windows x64 sem Python; iniciar sem internet; verificar prévia, FaceMesh, atalhos, persistência e encerramento. Reiniciar Windows e repetir. Testar atualização e desinstalação preservando configurações. O teste de Tk com mocks não substitui essa etapa.

A DLL experimental já adicionada ao ETS2 local pode ser removida com o jogo fechado: apenas MaxTrackBridge.dll e MaxTrackBridge-SCS-license.txt da pasta bin/win_x64/plugins. Nenhum controls.sii foi alterado nesta sessão.
