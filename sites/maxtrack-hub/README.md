# Max Hub · Guia de instalação e publicação

Esta pasta contém a loja, o painel administrativo e a API. O Hosting serve `public/`, o Authentication faz o login Google e a função `api` liga a loja ao Mercado Pago e ao Firestore. O instalador Windows fica no Hosting. O APK fica dentro da função e a API libera o download para contas com Max GPS ou Combo ativo.

O catálogo inicial usa pagamento único. MaxTrack Pro custa R$ 39,90, Max GPS R$ 29,90, Max Multimídia R$ 24,90 e o Combo R$ 69,90. Na primeira compra elegível, o Combo sai por R$ 59,90.

## Primeiro deploy do maxhub-ets2

O projeto já está selecionado no Firebase CLI e o domínio de Hosting confirmado é `https://maxhub-ets2.web.app`. O instalador 0.4.0 e o APK comercial foram preparados localmente para esse endereço.

1. No console Firebase, ative o plano Blaze, crie o Firestore padrão e habilite o login Google conforme o passo 2.
2. No Mercado Pago, cadastre a URL `https://maxhub-ets2.web.app/api/webhook` e configure os dois segredos de pagamento conforme o passo 3.
3. Cadastre a chave de licença que já foi gerada localmente. A partir da pasta deste README, execute:

   ```powershell
   firebase functions:secrets:set LICENSE_SIGNING_KEY --data-file '..\..\build\maxhub-signing\maxhub-license.pem' --project maxhub-ets2
   ```

4. Confira os arquivos do passo 5, faça o deploy pelo passo 6 e conceda sua permissão de administrador pelo passo 7.

As chaves desta release ficam em `../../build/maxhub-signing/`. Guarde essa pasta em um backup privado. O arquivo `android-password.dpapi` abre com a conta Windows que o gerou. Para compilar em outro usuário ou computador, preserve o certificado `maxgps.p12` e transfira a senha por um gerenciador de senhas.

## 1. Prepare o ambiente

- No Windows, tenha PowerShell, Node.js 22, Firebase CLI e Google Cloud CLI. O Java 21 é usado nos emuladores. Android Studio fornece o Java e as ferramentas de compilação do APK.
- Trabalhe com a pasta completa do MaxTrack. O script de release reutiliza o ambiente de compilação em `.build-venv`, o runtime Python 3.11 em `build/fps-package` e os binários, a telemetria, o extrator e a voz em `dist`. Preserve essas pastas ao copiar o projeto.
- No PowerShell, entre na pasta deste README. Instale o Firebase CLI se necessário e verifique as versões.

```powershell
Set-Location 'C:\Users\Pedro Max\Downloads\MaxTrack_v0.9\sites\maxtrack-hub'
node --version
npm install -g firebase-tools
firebase --version
firebase login
npm --prefix functions ci
```

Se o compilador do Inno Setup ou o Python estiver em outro local, passe `-Compiler` e `-PythonExe` com seus caminhos no passo 5. Se estiver usando o SDK Android do sistema, configure `ANDROID_HOME` para o SDK com Android Platform 35 e Build Tools 35.0.0. A pasta de trabalho atual já tem uma cópia das ferramentas Android em `build/android-tools`.

## 2. Configure o Firebase

1. Crie ou selecione um projeto no console Firebase e ative o plano **Blaze**. Use projetos separados para homologação e produção se for testar o checkout hospedado.
2. Em **Hosting**, o site deste projeto já está cadastrado em `https://maxhub-ets2.web.app`. Se usar outro domínio no futuro, ajuste-o em `STORE_ORIGIN`, no Mercado Pago e no parâmetro `-Origin` da compilação.
3. Em **Firestore Database**, crie o banco padrão `(default)` em modo de produção. O deploy instala as regras e os índices deste projeto.
4. Em **Authentication → Sign-in method**, habilite **Google** e escolha o e-mail de suporte. Em **Authentication → Settings → Authorized domains**, confira se o domínio do Hosting está autorizado. Se usar domínio próprio, conecte-o também ao Hosting.
5. O app web `maxhub-ets2` já foi registrado no Firebase. A loja lê a configuração pública em `/__/firebase/init.json` pelo próprio Hosting.

O Firebase CLI já aponta para `maxhub-ets2` nesta pasta. A variável `$origem` deve bater com o endereço mostrado no Hosting.

```powershell
$projeto = 'maxhub-ets2'
$origem = 'https://maxhub-ets2.web.app'
firebase projects:list
@("STORE_ORIGIN=$origem", "MP_SANDBOX=false") |
  Set-Content -Encoding ascii "functions/.env.$projeto"
```

Use `MP_SANDBOX=true` e o ID do projeto de homologação para fazer os testes descritos no passo 8.

[Configuração do Hosting](https://firebase.google.com/docs/hosting/quickstart) · [Login Google no Firebase](https://firebase.google.com/docs/auth/web/google-signin) · [Parâmetros e segredos das Functions](https://firebase.google.com/docs/functions/config-env)

## 3. Configure o Mercado Pago

1. Em **Mercado Pago Developers → Suas integrações**, crie ou abra a integração do **Checkout Pro**. Gere um novo Access Token antes de publicar, pois o anterior foi compartilhado na conversa.
2. Em **Webhooks**, selecione o ambiente correto e configure o evento **Pagamentos**. A URL de produção é `https://maxhub-ets2.web.app/api/webhook`.
3. Cadastre o Access Token e o segredo de assinatura dos Webhooks como dois segredos distintos. O Firebase pede cada valor no terminal.

```powershell
firebase functions:secrets:set MP_ACCESS_TOKEN --project $projeto
firebase functions:secrets:set MP_WEBHOOK_SECRET --project $projeto
```

O token e o segredo ficam no Secret Manager. O retorno do navegador só ajuda o cliente a voltar ao pedido. A chave é liberada após a API verificar a confirmação do pagamento no Mercado Pago.

[Credenciais do Mercado Pago](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro-orders/resources/credentials) · [Webhooks de pagamento do Checkout Pro](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro-preferences/payment-notifications)

## 4. Gere as chaves uma vez

Para `maxhub-ets2`, reutilize as chaves existentes em `../../build/maxhub-signing/`. Use os comandos deste passo para começar um ambiente novo. Guarde cópias das três chaves para as futuras versões.

| Chave | Para que serve |
| --- | --- |
| `maxhub-update.pem` | Assina o manifesto de atualizações Windows. Fica com você. |
| `maxhub-license.pem` | Assina os recibos de ativação. A função usa esse segredo no Firebase. |
| `maxgps.p12` | Assina os APKs. Use o mesmo certificado e alias para instalar novas versões por cima. |

```powershell
$chaves = Join-Path $env:USERPROFILE 'MaxHub-Chaves'
New-Item -ItemType Directory -Force $chaves | Out-Null

node .\release.mjs keygen "$chaves\maxhub-update.pem"
node .\release.mjs keygen "$chaves\maxhub-license.pem"
node .\release.mjs public "$chaves\maxhub-license.pem" "$chaves\maxhub-license-public.pem"
firebase functions:secrets:set LICENSE_SIGNING_KEY --data-file "$chaves\maxhub-license.pem" --project $projeto

keytool -genkeypair -keystore "$chaves\maxgps.p12" -storetype PKCS12 -alias maxgps -keyalg RSA -keysize 2048 -validity 10000
```

Se `keytool` estiver fora do PATH, use o executável em `C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe`. Os binários Windows incluem somente as chaves públicas de verificação.

## 5. Compile o instalador e o APK

O primeiro pacote de `maxhub-ets2` já foi compilado. Para recompilar esta máquina em uma versão futura, use as chaves existentes e carregue a senha Android protegida pelo Windows:

```powershell
$chaves = (Resolve-Path '..\..\build\maxhub-signing').Path
$senhaAndroid = Get-Content "$chaves\android-password.dpapi" | ConvertTo-SecureString
```

Se estiver usando uma chave Android própria, troque a leitura acima por `Read-Host -AsSecureString`. Em seguida:

```powershell
$env:MAXGPS_ANDROID_STORE_PASSWORD = [System.Net.NetworkCredential]::new('', $senhaAndroid).Password
try {
  .\build-release.ps1 -Origin $origem `
    -SigningKey "$chaves\maxhub-update.pem" `
    -LicensePublicKey "$chaves\maxhub-license-public.pem" `
    -AndroidKeyStore "$chaves\maxgps.p12" -AndroidKeyAlias maxgps `
    -Version 0.4.0 -AndroidVersionCode 7
} finally {
  Remove-Item Env:MAXGPS_ANDROID_STORE_PASSWORD -ErrorAction SilentlyContinue
}
```

Se a sua chave Android tiver uma senha própria, forneça também `MAXGPS_ANDROID_KEY_PASSWORD` durante a compilação e remova a variável no final. Quem usava um APK de teste com outro certificado pode precisar desinstalá-lo para a primeira instalação comercial. Isso apaga os dados locais do app.

Confira os artefatos gerados:

| Caminho | Uso |
| --- | --- |
| `public/downloads/releases/0.4.0/MaxHub-Setup.exe` | Instalação inicial e atualização do Windows |
| `public/downloads/update.json` e `update.sig` | Versão, SHA-256, tamanho e assinatura que o Hub verifica |
| `functions/private/MaxGPS-Android.apk` | Download autenticado via API |

Se o script informar que já existe um instalador diferente com o mesmo número, aumente a versão antes de gerar outra release. O Hosting trata o instalador daquela versão como imutável.

## 6. Publique e confira o endereço

Ainda na pasta deste README, rode:

```powershell
firebase deploy --only firestore,functions,hosting --project $projeto
Invoke-RestMethod "$origem/api/catalog"
Invoke-RestMethod "$origem/downloads/update.json"
```

Abra a loja no endereço escolhido. Confira o catálogo, o botão **Baixar para Windows**, o login por Google e a página **Minha conta**. Confira também se o manifesto retorna a versão compilada e se o APK aparece apenas depois de ativar uma licença elegível na conta.

## 7. Ative seu painel e crie chaves para testar

1. Entre uma vez na loja com a conta Google que será administradora.
2. Faça login no Google Cloud CLI com uma conta autorizada a administrar o Authentication nesse projeto e aplique a permissão.

```powershell
gcloud auth application-default login
node .\functions\admin.mjs $projeto 'seu-email@gmail.com' grant
```

3. Saia e entre de novo na loja. A conta abre na **Visão geral**. Selecione a aba **Administração**, use **Consultar pedidos** ou crie uma chave de teste escolhendo o produto e a validade. A aba fica disponível para a conta que recebeu a permissão `maxAdmin`.
4. Para testar no Windows, baixe o Hub pelo site e cole a chave em **Ativar com chave**. Feche o jogo e o MaxTrack, use **Configurar todos os perfis ETS2** e abra o perfil no jogo. O Hub faz backup dos controles locais e do Steam Cloud antes de atualizá-los. Com Max GPS ativo, a telemetria também pode ser instalada pelo botão **Instalar telemetria**.
5. Para testar o APK, entre na loja com a conta Google do testador e vincule a chave de teste de GPS ou Combo à conta. Baixe o APK em **Minha conta**, ative a chave no Hub, conecte PC e celular à mesma rede e informe o código de pareamento no Android. No Hub, use **Gerar mapa do ETS2** e **Testar voz no PC** para conferir essas funções.

Substitua `grant` por `revoke` no comando administrativo se precisar retirar a permissão da conta. As chaves de produto podem ser revogadas no painel.

## 8. Teste o checkout antes de divulgar

- Em um projeto de homologação, prepare a loja para `MP_SANDBOX=true` e configure as credenciais e o webhook do ambiente de testes. Use a conta compradora e o cartão de teste fornecidos pelo Mercado Pago.
- Verifique se o preço do checkout corresponde ao catálogo e se o redirecionamento volta para **Minha conta**. No painel do Mercado Pago, use **Enviar teste** para conferir a entrega no endpoint. Pagamentos com credenciais de teste podem ficar sem notificação automática. A simulação do painel testa a entrega do webhook. A suíte de emuladores abaixo testa a emissão da chave, as notificações repetidas e o reembolso com dados de teste.
- Na produção, use a origem definitiva, `MP_SANDBOX=false`, as credenciais de produção e a assinatura do webhook de produção. Confira o resultado do primeiro pagamento aprovado no painel e na conta do comprador antes de divulgar a loja.

[Compras de teste e contas compradoras](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro-preferences/integration-test/test-purchases) · [Simulador e entrega de notificações](https://www.mercadopago.com.br/developers/pt/docs/checkout-pro-preferences/payment-notifications)

## 9. Publique as próximas versões

1. Repita o comando do passo 5 com a mesma origem e as mesmas chaves. Aumente a versão Windows e o código Android, por exemplo `-Version 0.4.1 -AndroidVersionCode 8`.
2. Publique o Hosting e a função juntos quando mudar o instalador e o APK. Se alterar regras ou índices, inclua também `firestore`.

```powershell
firebase deploy --only functions,hosting --project $projeto
```

3. Abra a release anterior do Hub e confirme que ele encontra a nova versão. Com o jogo e o MaxTrack fechados, clique para atualizar. O Hub verifica a assinatura e o arquivo, instala e reabre. Quem ainda está na prévia 0.3.3 precisa instalar a primeira edição comercial uma vez.
4. No Android, baixe o APK novo pela conta e instale-o sobre a versão comercial anterior. Mantenha o certificado e aumente o código a cada release.

Para alterar apenas a aparência da loja, edite os arquivos em `public/` e publique com `firebase deploy --only hosting --project $projeto`. Os preços vêm de `functions/domain.js`. Se mudar os preços, atualize também a vitrine em `public/index.html` e os valores de contingência em `public/store.js`, depois publique Hosting e Functions.

Para uma atualização apenas do Hub Windows, use `-WindowsOnly` no script de release. Ele reutiliza o APK existente em `functions/private/`. Publique a nova release com `firebase deploy --only hosting --project $projeto`.

## Testes locais

A área do cliente abre com um resumo. As chaves ficam em **Meus produtos → Ver chave de ativação**, os downloads elegíveis ficam nessa mesma aba e as compras ficam em **Pedidos**. Quem clicou em Comprar antes de entrar segue para a confirmação do produto ao fazer login.

Os avisos animados da vitrine usam o aumento real no contador de compradores confirmados desde a consulta anterior. A consulta ocorre a cada 45 segundos com a página visível. No painel administrativo, **Testar animação de venda** mostra um exemplo identificado como demonstração.

```powershell
npm --prefix functions test
firebase emulators:exec --only firestore,auth --project demo-maxhub 'node --test functions/domain.test.js functions/emulator.test.js'
```

A suíte completa usa os emuladores Auth e Firestore e simula o Mercado Pago. Para conferir apenas a vitrine no navegador, execute `firebase emulators:start --only hosting --project demo-maxhub` e abra `http://localhost:5000`. O login Google real e o checkout funcionam no projeto Firebase configurado. Para compilar um instalador de ensaio, use `build-release.ps1 -TestBuild -Destination <pasta-separada>` com origem e chaves de teste.

## Se algo falhar

### Administração não aparece após entrar

Confira a conta usando o e-mail exato do login Google:

```bat
node functions/admin.mjs maxhub-ets2 seu-email@gmail.com status
```

Se a conta estiver sem a permissão, execute:

```bat
node functions/admin.mjs maxhub-ets2 seu-email@gmail.com grant
```

O script configura o projeto de cotas da autenticação local e confere se a permissão foi salva.
Se o Google pedir uma nova autenticação, execute `gcloud auth application-default login`
com a conta administradora do projeto. Depois da mensagem de permissão confirmada,
abra Minha conta na loja e clique em Atualizar conta. O botão renova a sessão para
carregar a permissão. Essa melhoria do botão precisa do deploy do Hosting.

### Hub mostra erro de conexão na ativação e na atualização

A versão 0.4.2 corrige uma falha ao iniciar o HTTPS no executável Windows.
Instale a versão corrigida pela primeira vez usando o instalador local em
`public/downloads/releases/0.4.2/MaxHub-Setup.exe`. Para disponibilizá-la
na loja e no atualizador, publique o Hosting:

```bat
firebase deploy --only hosting --project maxhub-ets2
```

Para verificar a comunicação sem digitar uma chave comprada, execute o Hub
instalado pelo Prompt de Comando:

```bat
"%LOCALAPPDATA%\Programs\MaxTrackPro\MaxHub.exe" --diagnostico-loja "%TEMP%\maxhub-conexao.json"
```

Abra `%TEMP%\maxhub-conexao.json` após alguns segundos. O relatório informa a
versão, o endereço da loja, a consulta de atualização e o resultado HTTP da
ativação com uma chave fictícia. HTTP 403 com mensagem de chave inexistente
nesse teste confirma que a rota respondeu. A chave comprada continua sendo
validada pela opção Ativar com chave na interface do Hub.

### Corrigir um segredo informado errado no primeiro deploy

Abra o Prompt de Comando e execute os comandos na pasta da loja.

```bat
cd /d "C:\Users\Pedro Max\Downloads\MaxTrack_v0.9\sites\maxtrack-hub"
firebase functions:secrets:set MP_ACCESS_TOKEN --project maxhub-ets2
firebase functions:secrets:set MP_WEBHOOK_SECRET --project maxhub-ets2
firebase functions:secrets:set LICENSE_SIGNING_KEY --data-file "..\..\build\maxhub-signing\maxhub-license.pem" --project maxhub-ets2
firebase deploy --only functions:api --project maxhub-ets2
```

No primeiro prompt, cole o Access Token de produção do Checkout Pro. No segundo, cole a assinatura secreta do webhook **Pagamentos** da mesma integração. A chave de licença é lida do arquivo gerado para a release 0.4.0, então o terceiro comando dispensa colar texto. Se o CLI oferecer atualizar a função antes de terminar os três comandos, responda `N` e faça a atualização no último comando.

Depois de atualizar a função, teste uma chave do painel no Hub. No Mercado Pago, confira as entregas do webhook para o endereço `https://maxhub-ets2.web.app/api/webhook`. O catálogo público pode abrir mesmo com os segredos incorretos.

| Sintoma | Onde conferir |
| --- | --- |
| Google diz que o domínio não é autorizado | Confira o domínio em Authentication e abra `/__/firebase/init.json` no endereço da loja para verificar se aponta para o projeto correto. |
| A loja abre e o catálogo não carrega | Abra `/api/catalog`. Confira o deploy da função `api` em `us-central1`, o Firestore padrão e os logs com `firebase functions:log --only api --project $projeto`. |
| A conta ou o Firestore retorna permissão negada no servidor | No Google Cloud IAM, confira a conta de serviço usada pela função. Ela precisa de acesso ao Firestore e de leitura ao Firebase Authentication para validar sessões. Confira também se a função consegue acessar os três segredos configurados. |
| Pagamento aprovado continua pendente | Confira o evento **Pagamentos**, a URL, o ambiente e a assinatura no painel de Webhooks. Veja o histórico de entregas e os logs da função. |
| O APK não aparece | Entre com a conta que possui GPS ou Combo ativo. Confira se `functions/private/MaxGPS-Android.apk` existia quando fez o deploy das Functions. |
| O Hub não aceita a atualização | Confira se o site serve `update.json` e `update.sig` da mesma release, se o arquivo publicado é o mesmo do manifesto e se a chave de atualizações é a mesma que gerou a versão instalada. |
| O instalador informa `ISCmplr.dll` inválida | Aponte `-Compiler` para o `ISCC.exe` de uma instalação íntegra do Inno Setup. |
| O GPS no celular não conecta | Mantenha o Hub aberto e os dois dispositivos na mesma rede local. Permita o Hub no firewall da rede privada e, se a descoberta falhar, use o endereço manual do Hub. |
