# Bridge SCS experimental

Código próprio baseado nas declarações públicas do SDK oficial 1.16. Não usa OpenTrack, FreeTrack, NPClient ou SDK TrackIR. A licença do SDK está em ../vendor/scs_sdk/sdk_license.txt e deve acompanhar a distribuição.

Compilar com Visual Studio C++ x64 e CMake:

```
cmake -S bridge -B build/bridge -A x64
cmake --build build/bridge --config Release
```

Com o jogo fechado, copiar MaxTrackBridge.dll para bin/win_x64/plugins na instalação do ETS2 ou ATS. Preservar outros plugins. Remover apenas esta DLL para desfazer. Abrir o jogo, aceitar o aviso de SDK se apresentado, verificar no game.log.txt a mensagem MaxTrack bridge e procurar o dispositivo MaxTrack Pro Experimental nas configurações de controle. Ativar a opção Bridge SCS no MaxTrack. Não executar ETS2 e ATS simultaneamente: a porta é exclusiva.

O dispositivo fornece yaw normalizado por 180 graus e pitch por 90 graus. Não há filtro adicional. O motor original continua calculando a pose. O plugin neutraliza os eixos após 500 ms sem pacote e limita a leitura a 64 datagramas por quadro. A vinculação desses eixos à câmera, seus sinais e a escala precisam ser confirmados no jogo; este plugin NÃO é uma implementação automática comprovada de head tracking. Não modificar controls.sii sem backup e sem confirmar as expressões suportadas pela versão instalada.

Estado: DLL compilada em build/bridge/MaxTrackBridge.dll com Zig 0.13.0, carregamento e exports verificados no Windows. Teste nativo aprovado (registro SDK, UDP, normalização, NaN, timeout, reinício). Ainda não carregada pelo jogo. Não anunciar integração direta funcional. O modo UDP 4242/OpenTrack permanece padrão. O instalador apenas inclui a DLL em sua própria pasta, não descobre nem modifica instalações dos jogos.

O script build-portable.ps1 reproduz compilação e teste usando o compilador portátil. O workflow executa o teste via CTest com MSVC. As duas ferramentas de compilação ainda não foram comparadas; apenas Zig foi executado localmente.
