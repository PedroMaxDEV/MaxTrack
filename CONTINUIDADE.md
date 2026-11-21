# Max Hub · continuidade entre MAX e JOAO

Última atualização em 20/11/2026, informada pelo ambiente do usuário.
Responsável por este registro, MAX. Data de trabalho da conversa anterior,
17/11/2026. Atualize a data quando houver nova intervenção.

## Comece por aqui

Leia este arquivo e AGENTS.md antes de trabalhar. Este é o resumo do projeto
para continuar em outra máquina sem depender do histórico do chat.
MAX identifica esta frente do Pedro. JOAO identifica a frente do amigo.
Abra uma branch por tarefa, registre o resultado aqui e integre por pull request.
Instruções de Git estão em COMPARTILHAR-GITHUB.md.

## Objetivo e estado real

Hub Windows com MaxTrack Pro, Max GPS e Max Multimídia. Loja Firebase com Google
Login, Mercado Pago, chaves de ativação, painel administrativo e releases assinadas.
O usuário controla a publicação. Ainda existem falhas e recursos incompletos.
O código e os pacotes de teste não comprovam que toda a experiência no ETS2 e no
Android físico funciona. Os relatos abaixo têm prioridade sobre descrições
otimistas de versões anteriores.

## Prioridades informadas pelo usuário

1. MAXTRACK. Ao voltar a olhar para frente, o usuário relata que a cabeça/câmera
   fica com movimento preso ou angulado. Ao aproximar e virar, quer uma visão
   muito ampla à esquerda e à direita para ver tráfego, com transição suave.
   Último relato ainda aponta inclinação/centralização inadequada. Reproduzir
   com câmera real e ETS2 antes de declarar corrigido. Inspecionar solvePnP,
   fallback, referência de aproximação, recenter F10 e suavização.
2. GPS/MAPAS. Usuário relatou falhas ao obter e baixar mapa mod com várias partes.
   Há extração pelo Truck Dash incluído no instalador e transferência ao APK.
   Foi gerado um grafo local de cerca de 2,34 MB e testada a entrega HTTP.
   Compatibilidade com o mod específico do usuário e download no telefone dele
   seguem sem confirmação. SDK oferece posição/distância/tempo/limite, e não
   fornece diretamente o desenho completo da rota. Não prometer qualquer mapa.
3. ATIVAÇÃO/ATUALIZAÇÃO. Hub 0.4.0 tinha falha de HTTPS no executável empacotado.
   0.4.2 usa WinHTTP do Windows e passou na consulta ao site e na rejeição
   esperada de uma chave fictícia. Compra/chave real do usuário ainda precisa
   ser confirmada no Hub. Não atribuir toda falha restante a conexão.
4. MULTIMÍDIA. Atualmente painel flutuante sobre jogo em janela sem borda,
   redimensionamento/expansão e comandos pelo celular. Integração gráfica
   de tablet dentro da cabine e extensão real de monitor continuam pendentes.
   O exemplo visual pedido pelo usuário é multimídia integrada na cabine.
5. LOJA. Fluxo local reorganizado com visão geral, produtos, pedidos e aba
   administrativa. Chaves reveladas por ação explícita. Animações e notificações
   usam aumento real de compradores. Demonstração identificada no painel.
   A última correção do botão Atualizar conta força renovação do token Google.
   Confirmar deploy e sessão reais antes de dizer que já está publicado.

## Versões e integração

- Firebase projectId maxhub-ets2, Hosting https://maxhub-ets2.web.app.
- Windows comercial mais recente preparado localmente, Hub 0.4.2.
- APK comercial permanece 0.4.0, versionCode 7. Atualização Windows 0.4.2
  reutilizou esse APK via -WindowsOnly.
- Manifesto local em sites/maxtrack-hub/public/downloads/update.json.
  A versão remota pode divergir até o usuário publicar o Hosting.
- Conta administrativa solicitada pelo dono foi concedida e confirmada no
  Firebase em 17/11/2026. Consulte o dono para identificar a conta em novas
  concessões. Script permite consultar status por e-mail sem revelar credenciais.
- Pagamento único. Track 39,90, GPS 29,90, mídia 24,90, combo 69,90,
  combo de primeira compra elegível 59,90 BRL. Backend é a referência de preço.
- Checkout Pro Preferences, webhook evento payment, mostrado pelo painel
  Mercado Pago como Pagamentos (legacy). Segredos no Secret Manager.

## Onde alterar

| Área | Arquivos principais |
| --- | --- |
| Pose, webcam, UDP, F9/F10 | maxtrack.py, stabilization.py, interface.py |
| Preferências por perfil | settings_store.py |
| Ponte SCS e eixos | bridge/bridge.cpp, vendor/scs_sdk/include |
| Todos os perfis e backup | ets2_install.py, game_config.py |
| Hub e integração | hub/desktop.py |
| Telemetria e API local | hub/telemetry.cpp, hub/server.py |
| Extração de mapa | hub/map_builder.py |
| Multimídia e comandos | hub/tablet.py, hub/media.py |
| Android nativo | hub/android/src/com/maxhub/gps |
| Licenças, HTTPS, atualização | max_store.py, max_store_winhttp.py |
| Loja que deve ir ao Hosting | sites/maxtrack-hub/public |
| Pagamentos e licenças Firebase | sites/maxtrack-hub/functions |
| Administrador | sites/maxtrack-hub/functions/admin.mjs |
| Build comercial portátil | build-support/build.ps1, build-support/README.md, .github/workflows/commercial-release.yml |
| Build comercial legado | sites/maxtrack-hub/build-release.ps1, release.mjs |
| Patch do runtime legado | installer/patch_legacy_maxtrack.py |
| Instalador | installer/MaxTrackPro.iss |
| Deploy e segredos | sites/maxtrack-hub/README.md |

sites/maxtrack-hub/dist é uma página antiga e não é o diretório do Hosting.
docs/RELEASE_STATUS.md e outros documentos antigos descrevem fases anteriores.
Use o presente registro para entender o que falta, e o código para verificar.

## Ambiente e testes

Fonte Windows em C:\Users\Pedro Max\Downloads\MaxTrack_v0.9.
Python 3.11 é necessário para o runtime legado MaxTrack/MediaPipe empacotado.
Dependências em requirements.txt e requirements-build.txt. Backend Node 22.

Comandos leves na raiz:

    python -m unittest discover -s tests
    npm --prefix sites/maxtrack-hub/functions ci
    npm --prefix sites/maxtrack-hub/functions test
    node --check sites/maxtrack-hub/public/store.js

O teste de UDP exige loopback liberado. Backend tem testes com emuladores
Firestore/Auth, documentados no README da loja. Foram aprovados 21 testes Python
e 7 testes backend com emuladores em etapas anteriores. Testes de compra usaram
Mercado Pago simulado. APK foi compilado e assinatura verificada. Não há prova de
execução física Android nas últimas alterações. Faça testes dirigidos à mudança.

## O que outra máquina precisa

O novo fluxo build-support/build.ps1 recompila os fontes com Python 3.11,
MSVC/CMake, Node 22 e JDK 17. Recursos de voz/mapa, ferramentas Android e Inno
estão nos três arquivos build-support/resources/*.zip rastreados por Git LFS.
O workflow comercial manual instala as ferramentas do runner e entrega ZIP de
deploy com site, funções, APK e instalador assinado. Veja build-support/README.md.
A primeira compilação completa no GitHub ainda está pendente; o repositório
remoto ainda precisa ser criado pelo usuário.

Para desenvolver a fonte, instale Python 3.11/Node 22, crie seu próprio ambiente
e instale requirements. Fonte em modo desenvolvimento funciona sem ativação.
Para compilar DLLs, use SDK SCS incluído e CMake/Visual Studio ou MinGW.
Para APK, use Android Platform 35/Build Tools 35 e Java do Android Studio.

O script legado sites/maxtrack-hub/build-release.ps1 ainda depende destes
arquivos locais. Use o novo fluxo portátil ao compilar em outra máquina:

- dist/MaxTrackPro com _internal e bridge, dist/installer-tools.
- dist/MaxHub/telemetry, voice e map-tools, com licenças dos fornecedores.
- build/fps-package com Python 3.11 e MaxTrackPro-original.exe.
- Ambiente .build-venv válido no novo computador, Inno Setup e SDK Android.
  Ambientes virtuais copiados podem conter caminhos antigos e precisar recriação.
- Configuração e chaves de produção, somente para quem vai assinar/publicar.

As chaves existentes estão em build/maxhub-signing, ignorado pelo Git.
Incluem atualização RSA, assinatura de licença RSA e certificado Android.
android-password.dpapi é protegido pela conta Windows que o criou.
Para mudar a máquina de assinatura, transfira a senha via canal privado.
Mantenha as mesmas chaves para atualizar os clientes existentes.
Não coloque credenciais do Mercado Pago, PEMs, P12 ou DPAPI no Git.
O pacote build-support/signing.enc contém as assinaturas necessárias à build
com criptografia AES-256-GCM. A senha está em build-support/backup-password.txt,
ignorado pelo Git; cadastre-a como secret MAXHUB_BUILD_PASSWORD no Actions.
A chave privada de licença do backend não está nesse pacote. A restauração
ocorre em build/signing-restored, também ignorado. Não gere novos certificados
para substituir os existentes, pois isso quebra atualizações e assinaturas.

## Registro de entregas e pendências

- 20/11/2026 · MAX · Preparada build portátil completa e workflow manual Windows.
  Incluídos recursos grandes por LFS, assinatura criptografada, compilação dos
  plugins, MaxTrack, Hub, helper e APK, e ZIP de deploy Firebase. Verificados os
  checksums dos três ZIPs, sintaxe PowerShell/Node e restauração das assinaturas
  comparada aos originais. Pré-verificação Git: 158 arquivos candidatos; três
  ZIPs e pacote criptografado incluídos, senha e chaves brutas excluídas.
  Guias de build e GitHub atualizados. Primeira build
  completa no Actions pendente após criar o repositório e cadastrar o secret.
  Nenhum deploy nem envio ao GitHub realizado. Bugs de jogo seguem pendentes.

- 17/11/2026 · MAX · Hub comercial 0.4.0, APK 0.4.0, loja e funções implementados.
  Compra real e modos de jogo completos permanecem sujeitos à validação do dono.
- 17/11/2026 · MAX · Hub 0.4.2 com HTTPS WinHTTP. Consulta ao manifesto assinado
  e ativação fictícia no executável verificadas. Instalação no PC do usuário,
  ativação da chave real e deploy da release seguem para confirmação.
- 17/11/2026 · MAX · Fluxo de conta e animações locais conferidos no navegador
  com dados isolados. Permissão administrativa do dono concedida e confirmada.
- 17/11/2026 · MAX · Continuidade e regras para as duas frentes criadas.
  Gitignore reforçado e guia de colaboração preparado. Nenhum bug de câmera,
  mapa ou multimídia foi corrigido nesta intervenção.
  Pré-verificação Git encontrou 144 arquivos candidatos, nenhum com 100 MiB
  ou mais e nenhum com os padrões procurados de token Mercado Pago ou chave
  privada. Essa verificação por padrões tem alcance limitado. Repositório remoto
  ainda não criado e nada enviado ao GitHub nesta intervenção.

Próxima ação sugerida, escolher uma frente/branch e reproduzir o bug de
centralização e olhar lateral com o usuário. A outra frente pode investigar
o mod de mapa específico, evitando editar os mesmos arquivos ao mesmo tempo.

## Modelo para a próxima atualização

Data · MAX ou JOAO · branch/tarefa.
Alterado e motivo.
Verificado com resultado.
Pendências e próxima ação.
Commit/PR quando houver.


## 20/11/2026 — JOAO — joao/centralizacao-maxtrack

Base 3d3b978 de main/origin/main. Checkout separado para preservar a frente MAX.
O filtro de saída mantinha cerca de ±0,6° no retorno após olhar pela janela.
Agora cada eixo volta a zero dentro do raio antitremor configurado. A ampliação
lateral por aproximação já estava implementada em CabinMotion.

Regressão reproduzida antes e aprovada depois, nos dois lados a 10/15/30/60 FPS
com pitch diferente de zero. Os 11 testes de estabilização passaram. Suíte
Python completa: 20 de 22 passaram, incluindo perfis locais e Steam simulados.
O teste de comparação depende de backups/original-0.9.8/maxtrack.py, ausente
do checkout. O teste UDP real expirou no loopback. O teste com captura do pacote
passou. Próxima ação: validar F10, volta ao centro e aproximação no ETS2 com
webcam real e observar se a estimativa facial ainda deixa desvio.

Diagnóstico das demais prioridades:
- GPS: o parser recebe a lista de mods, o gerador seleciona europe e exporta
  arestas entre nós. Android baixa por revisão e desenha grafo e rastro. Faltam
  o conjunto específico do mod e comparação de uma estrada ausente desde o
  log do extrator até o grafo no celular.
- Voz: checksum do pacote conferido. PcVoice.synthesize_local com Piper/Faber
  gerou WAV de 26682 amostras a 22050 Hz sem usar voz do sistema. Android usa
  TextToSpeech e tem fallback para áudio do Hub. Falta ouvir nos dois destinos.
- Multimídia: janela Windows sobreposta, atalho F8 e comandos do celular.
  SDK incluído expõe entrada e telemetria. Nenhuma implementação de textura
  de tablet na cabine identificada; requer protótipo com interior compatível.
- Loja: seis testes locais de domínio passaram e store.js passou na verificação
  de sintaxe. Compra, ativação real, atualização e sessão real seguem pendentes.
- Build comercial: MAXHUB_BUILD_PASSWORD e arquivo local de senha ausentes.
  Validar teste de regressão em checkout limpo e executar fluxo com credencial
  existente antes de entregar instalador, APK e ZIP. Publicação com Pedro.
  Alteração em commit local desta branch, sem PR publicado.

## 20/11/2026 — JOAO — joao/gps-mapas

Commit de implementação e382de6, sobre d66d023 da frente JOAO. PR pendente.
O teste com as seis partes locais do BR Brasil 6.1 identificou duas etapas
distintas. O parser leu brbrasil.mbd (1.030 setores) e o gerador original
abortou ao tratar um prefab isolado. O Hub agora consegue construir um grafo
a partir de sentidos de pista e conexões explícitas de curvas do prefab quando
o gerador falha. Amostra as curvas das estradas e identifica locais e faixas.
Os 12 trechos deste mod com definição de pista ausente ficam fora do roteamento
alternativo. O alcance do mapa é o dos dados que o extrator consegue interpretar.

O log real do perfil ativo indicava eldorado.mbd e cinco pacotes ME com cabeçalho
incompatível. A seleção automática verifica módulo e sessão e identifica pacotes
ilegíveis. Pode importar JSON externo compatível. Atualização por perfil é
opcional. A lista de mods mantém a ordem do log; a seleção manual depende da
ordem fornecida. O celular usa o grafo do Hub e mantém o rastro separado.

Android: mapa escuro, rota ciano, perspectiva/2D, giro por gesto, manobras
seguintes, indicação de faixas disponíveis, combustível e ETA SIM/REAL pela
escala local. Busca paradas próximas à rota e calcula rota para empresa e cidade
identificadas no frete. A rota calculada pode divergir das marcações do jogador
no navegador do jogo. QR usa o pareamento na rede local. Vozes Android usam
frases em 12 idiomas conforme a voz instalada; fallback integrado do PC em
português. O ambiente Python local não tem OpenCV para exibir QR; descoberta e
código seguem disponíveis. Checkout preparado para abrir o Hub em desenvolvimento.

Verificações nesta máquina:
- Entrada normal de build do mapa com os seis arquivos reais: grafo aceito pelo
  Hub, 87.705 nós, 91.279 segmentos, 1.825 indicações de faixa, 2.594 registros
  de postos, 6.136 de descanso, 464 de oficina e 2.117 de empresas. São registros
  do extrator, possivelmente múltiplos por instalação. Comparado ao resultado da
  conversão isolada. 79.343 nós alcançáveis a partir do primeiro nó.
- Cinco rotas entre cerca de 30 e 306 mil unidades calculadas pelo RoadMap Java
  em JVM, verificando cada ligação. Adaptadores de JSON usados nesse teste de
  lógica. Frases com distância exercitadas nas 12 línguas. Handler GET /mapa
  entregou o conteúdo com o SHA-256 esperado em memória. HTTP real local
  bloqueado por WinError 10013 nesta sessão.
- Três regressões GPS passaram. Suíte completa 23/25: backup histórico ausente
  e timeout UDP já registrados na tarefa anterior. Python compilou os módulos.
  DLL x64 compilada no MSVC com os dois exports SCS verificados; APK de
  desenvolvimento compilado e assinatura v2/v3 validada.
- Sem instalação no jogo ou telefone e sem publicação. Próxima ação: testar
  o BR Brasil no percurso conhecido, checar vias, sentidos, faixa, manobras,
  sincronização, voz e desempenho no aparelho. Para Eldorado, obter uma fonte
  compatível de estradas do autor. Não há validação de acesso fora da LAN,
  de equivalência à rota do jogo ou de cobertura de todos os mods. Pacote de
  produção depende da credencial comercial e das validações já pendentes.

## 20/11/2026 — JOAO — joao/gps-verificar-eldorado

Verificação de exportação para GPS. O log confirmou /map/eldorado.mbd.
Os cinco pacotes ME permitem listar um índice ZIP convencional com cinco
entradas cada e zero setores map/*.base visíveis. Nenhum grafo identificado
pela busca de JSON na pasta de documentos do jogo. O ts-map de dariowouters
documenta renderização e tiles para mods compatíveis. Não foi executado:
a consulta local de download no GitHub falhou na resolução de DNS.
O SDK incluído expõe posição do veículo e métricas do navegador. A telemetria
e o log não entregaram a malha rodoviária do Eldorado. Próxima ação para
este perfil: testar exportação de estradas compatível fornecida pela equipe.

Conversão Max GPS passou a conservar as cidades extraídas, X/Z, identificador
regional original e empresas. BR Brasil 6.1 reprocessado a partir dos dados
da extração real anterior: 398 cidades com empresas, 87.705 nós e 91.279
segmentos. Grafo, faixas e locais comparados à saída anterior; novo arquivo
aceito integralmente por read_map. Três testes de mapas aprovados. EAA, RBR,
renderização de cidades no Android e teste de jogo não verificados. Sem PR.

20/11/2026 — JOAO — joao/gps-estradas-desafiadoras. Teste de geração com os
dois arquivos locais do Estradas Desafiadoras: o parser identificou rotafg.mbd,
23 setores. O gerador alternativo produziu JSON aceito pelo Hub com 24 cidades,
6.757 nós e 7.032 segmentos. Sem download, alteração de código ou teste físico.
Próxima ação: comparar uma rota do mod no ETS2 com o mapa no aparelho. Sem PR.

## 21/11/2026 - JOAO - joao/validar-build-0.4.3

Ajustadas as definições de scs_input_init e scs_input_shutdown para compilar
com MSVC e as declarações do SDK. A bridge e a telemetria compilaram em Release
x64. dumpbin confirmou os dois exports da bridge. O teste bridge_transport
falhou no primeiro eixo recebido por UDP. Um teste independente de loopback UDP
também expirou. Repetir em ambiente com UDP funcional antes de liberar.

APK de desenvolvimento recompilado do commit f81d9ba. O APK comercial local
0.4.3 (8), pacote com.maxhub.gps, passou em apksigner v2/v3 e zipalign.
Manifesto, classes.dex e recursos coincidiram com a recompilação.
Sem teste no aparelho. Instalador e deploy pendentes: senha da assinatura
indisponível na sessão e DNS sem acesso ao GitHub e ao Hosting maxhub-ets2.
Próximo passo: rodar os testes e a build assinada com a credencial existente,
validar atualização no Android e publicar o pacote no Firebase.

21/11/2026 - JOAO - joao/validar-build-0.4.3. Teste de regressão passou
a comparar as cinco definições com uma referência versionada extraída do
commit inicial 3d3b978. A cópia antiga de backups não acompanha o Git.
Python 24/25, pendente recepção UDP local por timeout. Seis testes de domínio
da loja aprovados. APK 0.4.3 (8) com assinaturas v2/v3 e alinhamento válidos.
Preparado ZIP Android para Pedro publicar somente functions:api, com SHA-256
do APK conferido após empacotar. Testes no telefone e na loja publicada pendentes.
Para Windows, falta executar a build com MAXHUB_BUILD_PASSWORD e UDP funcional.
