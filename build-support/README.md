# Builds completas em outra máquina ou no GitHub

Os recursos grandes e a assinatura criptografada já estão preparados nesta pasta.
A compilação nova recria MaxTrack, Hub, assistente de instalação, plugins SCS e
APK a partir dos fontes. Ela gera um ZIP com a loja e os binários para deploy.
Esse caminho usa Python 3.11 normal e dispensa o runtime legado da máquina do Pedro.

## Primeiro envio ao repositório privado

O repositório precisa de Git LFS por causa dos pacotes Android e de voz.
Na raiz do projeto, antes de git add, rode:

    git init -b main
    git lfs install
    git add .gitattributes .gitignore
    git add .
    git diff --cached --stat
    git lfs ls-files

Na lista do LFS devem aparecer os três ZIPs em build-support/resources.
Depois faça commit e push seguindo COMPARTILHAR-GITHUB.md. O pacote signing.enc
leva a chave de atualização, a chave pública da licença e o certificado Android,
criptografados com AES-256-GCM. A senha fica no arquivo local
build-support/backup-password.txt, que está fora do Git.

A chave privada do servidor Firebase e os tokens Mercado Pago permanecem no
Secret Manager e na máquina do Pedro. A build usa a chave pública da licença.
Isso permite compilar e depois fazer deploy no projeto que já está configurado.

## Opção 1 · Build pelo GitHub Actions

1. No repositório privado, abra Settings → Secrets and variables → Actions.
2. Cadastre um repository secret chamado MAXHUB_BUILD_PASSWORD. Copie para ele
   o conteúdo de build-support/backup-password.txt. Guarde essa senha também em
   um gerenciador de senhas. O arquivo local permite acessar o pacote de assinatura.
3. Abra Actions → Max Hub - build comercial → Run workflow.
4. Informe uma versão nova, por exemplo 0.4.3, e código Android 8. Aumente ambos
   nas próximas releases. Execute na branch com os fontes que serão distribuídos.
5. Quando a execução terminar com sucesso, abra o resultado e baixe o artifact
   MaxHub-VERSAO-deploy. O GitHub entrega o artifact dentro de um ZIP. Extraia
   também o ZIP de deploy que estiver dentro dele.

A compilação roda no Windows com Visual Studio, Python 3.11, Node 22 e Java 17.
Os recursos de mapa, voz, Android e Inno são extraídos do próprio repositório.
O Actions verifica testes de fonte, bridge e autoteste do MaxTrack empacotado.
A primeira execução no GitHub ainda precisa ser validada após criar o repositório.

## Opção 2 · Build na máquina do amigo

Instale Git com LFS, Python 3.11 x64, Node 22, Java JDK 17 ou superior, CMake
e Visual Studio Build Tools com Desktop development with C++. Use PowerShell 7.
Tenha acesso à internet para instalar os pacotes Python e npm.

    git clone https://github.com/SEU_USUARIO/maxhub-ets2.git
    cd maxhub-ets2
    git lfs pull

Carregue a senha do pacote na sessão sem colocá-la no histórico e compile:

    $senha = Read-Host 'Senha de build fornecida pelo Pedro' -AsSecureString
    $env:MAXHUB_BUILD_PASSWORD = [System.Net.NetworkCredential]::new('', $senha).Password
    try {
      ./build-support/build.ps1 -Version 0.4.3 -AndroidVersionCode 8
    } finally {
      Remove-Item Env:MAXHUB_BUILD_PASSWORD -ErrorAction SilentlyContinue
    }

Se o comando python apontar para outra versão, acrescente -PythonExe com o
caminho do Python 3.11. Se o JDK estiver em outra pasta, passe -JavaHome.
Com Android Studio, o padrão de Java é C:/Program Files/Android/Android Studio/jbr.
Os recursos Android e o Inno já estão nos arquivos do repositório.

A assinatura é extraída para build/signing-restored. Essa pasta está ignorada.
Quem tiver a senha e o pacote poderá assinar atualizações. Compartilhe a senha
apenas com quem será responsável pelas builds e preserve os arquivos originais.

## Baixar no PC do Pedro e publicar

O resultado fica em build/portable-release/VERSAO/MaxHub-VERSAO-deploy.zip.
Ele contém maxtrack-hub/public, functions com APK, firebase.json, índices,
regras e configuração do projeto. Não é necessário copiar arquivos na mão.

Extraia o pacote em uma pasta nova, abra maxtrack-hub no terminal e rode:

    npm --prefix functions ci
    firebase login
    firebase deploy --only firestore,functions,hosting --project maxhub-ets2

Os segredos já cadastrados no Firebase são reutilizados. Confira no site o
manifesto /downloads/update.json e o novo número de versão. O Hub existente
verifica a assinatura da atualização com a mesma chave pública das versões
anteriores. Os APKs usam o certificado Android existente.

A build antiga 0.4.0 tem uma falha de comunicação HTTPS. Atualize uma vez pelo
instalador corrigido quando esse cliente não conseguir baixar pelo próprio Hub.
A versão 0.4.2 já contém a correção.

## O que está incluído

- Fontes dos três apps, loja, backend, plugins e instaladores.
- Voz Faber e runtime Piper com os arquivos e avisos de licença existentes.
- Extrator de mapas com verificação SHA-256.
- Android Platform 35 e Build Tools usados neste projeto.
- Inno Setup com seus arquivos auxiliares.
- Certificado Android e chave de atualização no pacote criptografado.
- Workflow manual e script local que recompilam tudo e geram o ZIP de deploy.

Os pacotes oficiais Python/npm e o JDK do Actions são instalados pelas ferramentas
de cada ambiente. Uma compilação bem-sucedida ainda exige testar câmera, mods de
mapa e APK com o jogo e dispositivos reais antes de anunciar suporte.

[Baixar artifacts no GitHub](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)

