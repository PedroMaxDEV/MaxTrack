# Trabalho compartilhado do Max Hub

Antes de investigar, editar ou compilar, leia CONTINUIDADE.md na raiz.
Use esse arquivo como ponto de entrada para o estado atual e as prioridades.
Consulte os arquivos específicos conforme necessário. Documentos antigos em docs/
podem descrever versões anteriores e devem ser interpretados pela data.

Ao iniciar, identifique qual frente está sendo executada e use uma branch própria.
Use MAX para o trabalho solicitado pelo Pedro nesta máquina. Use JOAO para a
frente do amigo, salvo se o usuário indicar outro nome. São identificadores de
trabalho e não indicam autoria humana do código.

Antes de concluir uma alteração, atualize CONTINUIDADE.md com o que foi alterado,
os testes executados, o que continua pendente e a próxima ação. Registre a data
e a assinatura MAX ou JOAO no histórico. Preserve os registros da outra frente.
Descreva o que realmente foi verificado. Só marque um bug resolvido depois de
verificar o caso que o usuário relatou.

Segredos e chaves privadas ficam fora do Git. Reutilize as chaves de assinatura
existentes ao gerar atualizações de produção. Confirme o domínio e a versão da
release. O usuário faz o deploy, conforme combinado nesta sessão. Uma solicitação
posterior explícita pode mudar essa autorização.

Mantenha mudanças pequenas para economizar contexto e revisão. Evite reler toda
a conversa, gerar documentação duplicada ou executar compilações longas quando a
tarefa exige apenas uma correção localizada. Não trabalhe sobre alterações ainda
não integradas da outra frente. Integre por pull request e resolva divergências
preservando os comportamentos solicitados.
