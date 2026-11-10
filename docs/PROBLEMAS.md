# Solução de problemas

**Prévia preta:** feche apps que usam a câmera, confira permissões do Windows e teste outro índice da webcam.

**Yaw/Pitch não mudam:** confira se o rosto é detectado e se o aplicativo está ativo (F9); centralize (F10). Evite luz atrás do rosto.

**OpenTrack parado:** Input UDP over network, porta 4242, Start; confira se não há conflito com outra instância.

**Jogo parado, mas OpenTrack mexe:** confirme Output freetrack 2.0 Enhanced, reinicie OpenTrack e jogo e revise as configurações de rastreamento do jogo.

**Movimento invertido:** use as opções de inverter horizontal/vertical do MaxTrack.

**Tremor/delay:** ajuste suavização, sensibilidade e iluminação; valores altos de suavização podem aumentar atraso.

**Erro MediaPipe solutions:** use Python 3.11 e as versões fixadas em requirements.txt; recrie o ambiente virtual.

**Executável não inicia:** extraia o ZIP completo (build onedir) e confira as mensagens de segurança do Windows; abra um issue com Windows, webcam e log/erro (sem dados pessoais).
