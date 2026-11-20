# Colaboração no GitHub · MAX e JOAO

Crie um repositório PRIVADO chamado maxhub-ets2 no GitHub, sem inicializar README, licença ou gitignore. Em Settings → Collaborators, convide a conta do amigo. Ele deve aceitar o convite com a conta dele.

## Primeiro envio na máquina do Pedro

Abra o Prompt de Comando na raiz do projeto. Troque SEU_USUARIO no endereço abaixo pela sua conta GitHub.

    cd /d "C:\Users\Pedro Max\Downloads\MaxTrack_v0.9"
    git init -b main
    git lfs install
    git add .gitattributes .gitignore
    git add .
    git diff --cached --stat
    git diff --cached --name-only

Confira a lista selecionada. Execute também git lfs ls-files: os três ZIPs em build-support/resources devem aparecer. O .gitignore exclui ambientes virtuais, node_modules, build, dist, backups, configuração pessoal, credenciais .env e chaves sem criptografia. Antes do primeiro commit, se aparecer algo confidencial, retire do índice com git rm --cached "caminho-do-arquivo" e ajuste o .gitignore. O arquivo local é preservado.

Depois da conferência:

    git commit -m "Organiza fontes e continuidade do Max Hub"
    git remote add origin https://github.com/SEU_USUARIO/maxhub-ets2.git
    git push -u origin main

Se o Git pedir sua identidade, rode git config user.name "Seu nome" e git config user.email "seu-email". O primeiro push pode abrir o navegador para autenticação. Este guia prepara o envio. O repositório remoto ainda precisa ser criado.

## Na máquina do amigo

    git clone https://github.com/SEU_USUARIO/maxhub-ets2.git
    cd maxhub-ets2
    git lfs pull
    git switch -c joao/corrigir-mapa

Cole esta mensagem na conversa da IA dele:

> Este é o projeto Max Hub compartilhado com o Pedro. Minha frente se chama JOAO. Leia AGENTS.md e CONTINUIDADE.md antes de alterar arquivos. Continue a tarefa combinada nesta branch. Ao terminar, registre mudança, testes, pendências e próxima ação em CONTINUIDADE.md, com data e assinatura JOAO. Descreva as dependências que faltarem na máquina. Confirme no jogo ou celular os comportamentos que dependem deles antes de marcar a tarefa concluída.

Para executar o MaxTrack por fonte e instalar dependências backend, na raiz:

    py -3.11 -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    .venv\Scripts\python.exe maxtrack.py
    npm --prefix sites/maxtrack-hub/functions ci

A compilação completa está preparada em build-support/README.md. Os recursos grandes vão pelo Git LFS e os certificados de build seguem criptografados em build-support/signing.enc. Cadastre MAXHUB_BUILD_PASSWORD nos secrets do GitHub Actions usando a senha do arquivo local build-support/backup-password.txt, que não vai para o Git. O workflow manual gera instalador, APK e ZIP de deploy para o Pedro baixar e publicar. Tokens do Mercado Pago e a chave privada de licença do servidor continuam fora do repositório.

## Trabalho diário

Antes de uma tarefa nova, salve o trabalho anterior em commit e comece da main atual.

    git switch main
    git pull --ff-only
    git switch -c max/corrigir-camera

O amigo usa branches como joao/corrigir-mapa. Ao concluir, atualizem CONTINUIDADE.md e publiquem a branch.

    git add .
    git diff --cached --stat
    git commit -m "Descreve a alteracao e a verificacao"
    git push -u origin HEAD

No GitHub, abram uma pull request da branch para main, revisem e integrem antes de atualizar a outra máquina. Evitem editar os mesmos arquivos simultaneamente. Se houver conflito no registro de continuidade, preservem as entradas das duas frentes e reconciliem as pendências.

Git sincroniza fontes e commits. Cada conversa deve ler CONTINUIDADE.md para recuperar o trabalho da outra frente. O histórico de chat permanece em cada conversa.

## Referência oficial

[Enviar projeto local ao GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github?platform=windows)
