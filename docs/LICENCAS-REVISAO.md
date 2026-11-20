# Revisão de distribuição — pendências explícitas

A ponte própria usa somente o SDK SCS 1.16, cuja licença está preservada em vendor/scs_sdk/sdk_license.txt e acompanha a DLL. Não inclui NPClient, SDK TrackIR ou código OpenTrack. O nome de mixes trackir no controls.sii é um identificador do jogo, não a implementação do protocolo TrackIR.

O inventário de pacotes e textos encontrados são coletados em THIRD_PARTY_NOTICES. Esse inventário inclui também ferramentas de build e não prova sozinho quais componentes nativos foram incorporados. Conferir o pacote final e preservar os avisos de cada biblioteca.

Fontes primárias para revisão:

- MediaPipe: https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE (Apache 2.0). Confirmar também os modelos e componentes presentes no wheel 0.10.21.
- OpenCV Python e componentes nativos: https://github.com/opencv/opencv-python/blob/4.x/LICENSE-3RD-PARTY.txt . Revisar o arquivo local do wheel efetivamente instalado, incluindo FFmpeg e demais componentes; não tratar tudo como uma única licença permissiva.
- PyInstaller e exceção para distribuição: https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt . Preservar a versão local dos termos.
- Inno Setup: https://jrsoftware.org/isorder.php e licença instalada em vendor/inno. Verificar as condições aplicáveis ao uso comercial do compilador.
- SDK TrackIR proprietário: https://trackir.com/developers . Não utilizado neste produto.

Antes de vender: resolver obrigações de fonte/relincagem quando aplicáveis, avisos Python/Tcl/Tk, modelos e bibliotecas nativas; definir titular, suporte e termos do produto. Não existe nesta revisão uma aprovação jurídica ou afirmação de conformidade comercial completa.
