# Histórico da implementação — não usar como estado atual

Este arquivo registra etapas anteriores e contém resultados que foram superados. Consulte RELEASE_STATUS.md para o estado consolidado atual.

## Instalador gerado

`dist/installer/MaxTrackPro-Setup.exe` gerado com sucesso pelo Inno Setup 6.7.4, contendo executável atualizado, dependências, DLL experimental e avisos de licença coletados. O compilador oficial teve assinatura Authenticode válida verificada antes da instalação. O instalador do MaxTrack não possui assinatura comercial. Ainda não houve validação em máquina limpa nem teste de webcam/jogo no pacote instalado. O instalador não configura automaticamente a câmera nos jogos.

## Atualização — perfis e teste de interface

Perfis ETS2/ATS independentes e salvamento automático após 700 ms implementados. Valores numéricos são validados antes de entrar no motor. Cinco testes unitários aprovados. Smoke test Tcl/Tk aprovado com webcam e atalhos simulados: criação dos widgets, troca/recuperação de perfis, gravação e encerramento. Isso NÃO comprova captura real ou atalhos globais.

DLL instalada em `C:/Program Files (x86)/Steam/steamapps/common/Euro Truck Simulator 2/bin/win_x64/plugins/MaxTrackBridge.dll`, acompanhada de MaxTrackBridge-SCS-license.txt. Não havia DLL anterior com esse nome. Para desfazer, fechar o jogo e remover somente esses dois arquivos. Perfil e controls.sii não foram alterados. A tentativa de abrir o jogo via controle de janelas não produziu janela; duas capturas da Steam falharam por timeout. Aguardando abertura manual para verificar log. Nenhum sucesso de integração no jogo foi registrado.

## Atualização mais recente — compilação nativa concluída

Executável Python recompilado com sucesso em `dist/MaxTrackPro/MaxTrackPro.exe`, incluindo Tcl/Tk e dependências MediaPipe. A pasta inteira é necessária. DLL da bridge e licença SCS incluídas em `dist/MaxTrackPro/bridge`; avisos disponíveis dos pacotes e inventário em THIRD_PARTY_NOTICES. Ainda sem teste interativo do executável, instalação limpa ou instalador Inno gerado. Não distribuir como versão comercial validada.

`build/bridge/MaxTrackBridge.dll` compilada para Windows x64 com Zig 0.13.0. O Windows carregou a DLL via ctypes e localizou scs_input_init/scs_input_shutdown. O executável de testes nativos passou: registro do dispositivo, rejeição de versão inválida/parâmetro nulo, recepção UDP, normalização dos eixos, fim da sequência de eventos, rejeição de NaN, neutralização após timeout e reinicialização. O teste simula as chamadas do SDK; NÃO é execução dentro do ETS2.

ETS2 encontrado localmente. Leitura do controls.sii confirmou mixes trackiron, trackiryaw, trackirpitch e headtr*. Nenhum arquivo do jogo foi modificado. A identificação do dispositivo SDK no jogo, unidade angular esperada pelos mixes e sinais continuam pendentes de validação. Não há evidência de movimento da câmera sem OpenTrack.

O primeiro empacotamento Python revelou falha de acesso Tcl/Tk sob isolamento. O teste fora do isolamento inicializou Tcl corretamente; o executável dessa primeira compilação não é uma entrega validada. Nova compilação solicitada com acesso adequado. As seções abaixo registram etapas anteriores; esta atualização prevalece quanto à compilação da bridge.

## Preservação e arquitetura

Backup: `backups/original-0.9.8`, com SHA256.json. Inclui todos os arquivos originais da raiz, inclusive configuração, scripts, log e ZIP. O ambiente .venv não foi duplicado; suas versões estão em environment-tested.txt. Para reverter, feche o aplicativo e copie maxtrack.py e config.json do backup para a raiz.

maxtrack.py contém interface Tkinter, captura DirectShow com fallback MSMF, FaceMesh local, solvePnP e fallback geométrico. A pose relativa ao centro passa por zona morta, sensibilidade, inversões, limites e filtro exponencial dependente de dt. F9 pausa; F10 centraliza. Saída UDP localhost:4242: seis doubles little endian, X/Y/Z/Yaw/Pitch/Roll. OpenTrack continua obrigatório nesta versão.

Os scripts INSTALAR e INICIAR usam o Python global; CRIAR_EXE usa .venv. O novo workflow usa ambiente Python 3.11 isolado no runner. O ZIP e log existentes foram preservados como artefatos históricos, não auditados integralmente. Dependências de .venv não são código próprio e não foram auditadas integralmente.

Alterações: preservação de configurações existentes sem sobrescrever inversões; gravação atômica da configuração; dados do executável em LOCALAPPDATA/MaxTrackPro; fechamento aguarda a thread de captura antes de fechar o socket. Uma captura travada pode manter a janela aberta; timeout/cancelamento nativo ainda precisa de teste.

## Evidência de testes

Executado no Windows: imports OpenCV/MediaPipe/NumPy/Pillow/pynput; py_compile; dois testes unittest aprovados. Os testes verificam igualdade estrutural dos métodos de rastreamento, pausa e centralização com o backup, contrato de pacote, envio/recepção UDP localhost e exemplos de zona morta/limites. Não equivalem a validação de câmera real ou qualidade do tracking.

Não executado: jogo, webcam real, interface interativa, compilação PyInstaller, Inno Setup, GitHub Actions, instalação limpa, desinstalação, funcionamento offline do pacote. Não existe MaxTrackPro-Setup.exe gerado nesta entrega. O workflow manual prepara esse nome, mas precisa ser executado em um repositório GitHub.

## Integração direta e licenças — investigação inicial

- SCS publica SDK com telemetria e dispositivos de entrada básicos: https://modding.scssoft.com/wiki/Documentation/Engine/SDK/Telemetry . Isso não prova uma API de escrita da câmera; validar os headers e exemplos do SDK antes de escolher essa rota.
- A interface FreeTrack e o adaptador NPClient são componentes diferentes: https://github.com/opentrack/opentrack/tree/master/freetrackclient e https://github.com/opentrack/opentrack/tree/master/contrib/npclient . Publicar memória compartilhada não instala um cliente reconhecido pelo jogo. Arquitetura, descoberta do cliente, sincronização, unidades, identificação e eventual handshake precisam ser validados.
- O SDK TrackIR é proprietário e tem termos específicos: https://trackir.com/developers . Não foi incorporado, nem foram copiadas DLLs ou código proprietário. A licença geral do OpenTrack não deve ser presumida para cada componente.
- Antes da venda, inventariar licenças dos wheels realmente distribuídos, bibliotecas nativas, modelos MediaPipe e empacotador, incluir notices e verificar redistribuição. Este inventário jurídico/comercial NÃO está concluído.

Game Bridge própria implementada em código-fonte experimental em `bridge/`, via dispositivo genérico do SDK SCS. Ainda NÃO compilada nem validada no jogo. Nenhuma alteração de registro, DLL de jogo ou configuração do ETS2 foi realizada. Não anunciar independência funcional de OpenTrack.

## Roteiro de aceitação manual

1. Rodar a cópia original com OpenTrack e registrar versão do jogo, FPS, câmera, configurações e movimentos em vídeo.
2. Rodar a versão atual com os mesmos ajustes; comparar esquerda/direita, cima/baixo, limites, tremor e resposta.
3. Testar F9, F10, ausência de rosto por mais de 0,65 s, desconexão/reconexão da webcam, detecção de webcams e fechamento durante captura.
4. Salvar, fechar e reabrir; confirmar inversões e valores preservados.
5. Compilar workflow e instalar em Windows x64 sem Python; testar webcam, atalhos, reinício, sem rede e desinstalação.
6. Quando existir bridge: fechar e impedir inicialização do OpenTrack, abrir ETS2, confirmar carregamento do cliente no log do jogo, testar todos os movimentos e repetir no ATS. Repetir em máquina sem OpenTrack instalado. Registrar evidência e versões antes de mudar o padrão.

## Trabalho restante

Compilar e validar a bridge e o vínculo dos eixos à câmera; perfis independentes ETS2/ATS, modernização visual, salvamento automático durante uso, auditoria completa de licenças, compilação/validação do instalador e testes reais nos jogos. Não há ativação implementada.

## Continuação — SDK oficial

SDK 1.16 obtido de https://download.eurotrucksimulator2.com/scs_sdk_1_16.zip; SHA-256: 49821E25568F4D7E462135F577F8FEF2AB197326404F2C1DAEF139B8F3DC5E69. Headers, exemplos e licença preservados em vendor/scs_sdk. A licença incluída permite uso e venda com preservação do aviso; isso não conclui a auditoria das demais dependências.

Bridge C++ registra dois eixos genéricos e recebe o pacote existente em localhost:4243; possui timeout neutro e socket não bloqueante. Seleção experimental adicionada à interface, mantendo OpenTrack como padrão. CMake e workflow preparados para compilar/incluir DLL e licença. Não foi encontrado compilador C++ nesta sessão. A configuração da câmera no jogo permanece uma questão em aberto: registrar eixos não comprova controle absoluto da câmera.

Teste adicional cobre seleção das portas e igualdade dos dados nos dois modos. Três testes automatizados aprovados; compilação sintática Python aprovada. Testes nativos e de jogo pendentes.
