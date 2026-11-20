# MaxTrack Pro — candidato em desenvolvimento

Não aprovado para lançamento comercial como aplicativo independente de OpenTrack.

## 0.9.11 — em validação

Usuário confirmou melhora de tremor na 0.9.10 e relatou lentidão nas viradas. A 0.9.11 introduz resposta adaptativa opcional, cabeçalho com FPS de captura, prévia fixa e ajustes em abas. Preferências salvas preservadas. Botão de ajuste rápido disponível para comparação. 14 testes aprovados; desempenho e estabilidade no jogo ainda dependem da comparação manual. Ver RESPOSTA-0.9.11.md.

## Validação manual informada pelo usuário — ETS2

Usuário confirmou movimentos de câmera com OpenTrack completamente fechado e Bridge SCS marcada. Relatou resposta suave, mas tremor significativo mesmo aumentando a suavização. Portanto, a integração direta tem validação manual do usuário no ETS2; estabilidade ainda reprovada. Não houve observação visual independente pelo agente. ATS não instalado/não testado.

Versão 0.9.10 adiciona anti-tremor configurável na saída (padrão 0,6 grau; zero desliga), mantendo os cálculos originais. 11 testes unitários e smoke test de widgets aprovados. Comparação real da redução de tremor pendente; ver ANTI-TREMOR.md.

O pacote anterior falhava ao importar NumPy. Corrigido usando `.build-venv` separado e requirements-build.txt: NumPy 1.26.4, MediaPipe 0.10.21 e OpenCV 4.11.0. O novo executável passou no autoteste real de Tcl/Tk e FaceMesh; abriu sua janela e o log confirmou abertura da webcam e inicialização FaceMesh. O ambiente original não foi reinstalado nem alterado. Esse autoteste agora faz parte do CI. A captura visual da janela ainda falha por timeout no controle de aplicativos.

Teste de webcam via fonte capturou 60 quadros; nenhum rosto foi detectado, portanto a qualidade de detecção/pose continua pendente. Não foram gravadas imagens.

Configuração experimental aplicada ao perfil local 4D4158454C com o jogo fechado; backup em controls.sii.maxtrack-backup. São sete mixes de head tracking. Identificadores sdk.maxtrack.yaw/pitch e escalas exigem confirmação no jogo; não tratar como integração comprovada. Restaurar o backup com o jogo fechado para retomar o caminho TrackIR/OpenTrack original. Não sobrescrever outras mudanças posteriores do perfil sem revisão.

## Concluído e verificado

- Backup original 0.9.8 com hashes, preservado.
- Motor de tracking, calibração, pausa e recenter estruturalmente iguais ao original, verificados por regressão.
- Perfis ETS2/ATS, validação e salvamento automático. Correção da persistência da webcam.
- Interface atualizada mantendo os controles, prévia e atalhos originais. Teste de widgets aprovado com câmera/atalhos simulados; revisão visual real pendente.
- DLL própria SCS compilada e teste nativo de transporte aprovado.
- Log real do ETS2 confirmou carregamento da DLL e registro do dispositivo maxtrack. Isso NÃO comprova movimento da câmera.
- Instalador anterior gerado; instalação e desinstalação de teste aprovadas. O binário distribuído deve ser recompilado após cada alteração de fonte.
- Preparação de alterações reversíveis de controls.sii com testes e aplicação experimental ao perfil local com backup. Identificadores e escala ainda experimentais.

## Impedimentos de lançamento

1. Confirmar redução de tremor da 0.9.10 e repetir yaw/pitch, F9/F10 e perda de rosto na cabine do ETS2 sem OpenTrack.
2. Validar ATS. Usuário informou que não está instalado; não anunciar suporte testado.
3. Validar webcam, atalhos e funcionamento offline no executável instalado em Windows limpo.
4. Completar instalação automática da ponte e configuração reversível por perfil; hoje o setup só inclui a DLL.
5. Revisar integralmente as obrigações das bibliotecas nativas e modelos distribuídos. Coleta de notices não equivale a auditoria concluída.

O teste de integração não pode ser substituído por testes de socket, registro do dispositivo ou carregamento de DLL. Nenhuma ativação implementada.
