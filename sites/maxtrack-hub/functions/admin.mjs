import { applicationDefault, initializeApp } from 'firebase-admin/app';
import { getAuth } from 'firebase-admin/auth';

const [projectId, email, action] = process.argv.slice(2);
if (!projectId || !email || !['grant', 'revoke', 'status'].includes(action)) {
  console.error('Uso: node admin.mjs <projeto-firebase> <email-google> <grant|revoke|status>');
  process.exit(1);
}
process.env.GOOGLE_CLOUD_QUOTA_PROJECT = projectId;
const auth = getAuth(initializeApp({ credential: applicationDefault(), projectId }));
const account = await auth.getUserByEmail(email);
if (action === 'status') {
  console.log(account.customClaims?.maxAdmin === true
    ? 'Esta conta tem permissão de administrador.'
    : 'Esta conta ainda não tem permissão de administrador.');
  process.exit(0);
}
const claims = { ...account.customClaims };
if (action === 'grant') claims.maxAdmin = true;
else delete claims.maxAdmin;
await auth.setCustomUserClaims(account.uid, claims);
if (action === 'revoke') await auth.revokeRefreshTokens(account.uid);
const confirmed = await auth.getUser(account.uid);
if ((confirmed.customClaims?.maxAdmin === true) !== (action === 'grant')) {
  throw new Error('O Firebase não confirmou a alteração da permissão.');
}
console.log(action === 'grant' ? 'Permissão concedida e confirmada. Na loja, clique em Atualizar conta.' : 'Permissão revogada e confirmada.');
