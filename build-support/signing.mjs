import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const [mode, source, destination] = process.argv.slice(2);
const password = process.env.MAXHUB_BUILD_PASSWORD;
if (!password || password.length < 20) throw new Error('Informe MAXHUB_BUILD_PASSWORD com pelo menos 20 caracteres.');
if (!['pack', 'unpack'].includes(mode) || !source || !destination) throw new Error('Use pack|unpack origem destino.');
const names = ['maxhub-update.pem', 'maxhub-license-public.pem', 'maxgps.p12'];
if (mode === 'pack') {
  const files = {};
  for (const name of names) files[name] = (await readFile(join(source, name))).toString('base64');
  if (!process.env.MAXGPS_ANDROID_STORE_PASSWORD) throw new Error('Informe a senha Android.');
  files.androidPassword = process.env.MAXGPS_ANDROID_STORE_PASSWORD;
  const salt = randomBytes(16), nonce = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', scryptSync(password, salt, 32), nonce);
  const encrypted = Buffer.concat([cipher.update(JSON.stringify(files), 'utf8'), cipher.final()]);
  await writeFile(destination, Buffer.concat([Buffer.from('MAXBUILD1'), salt, nonce, cipher.getAuthTag(), encrypted]));
} else {
  const data = await readFile(source);
  if (data.subarray(0, 9).toString() !== 'MAXBUILD1') throw new Error('Pacote de assinatura inválido.');
  const decipher = createDecipheriv('aes-256-gcm', scryptSync(password, data.subarray(9, 25), 32), data.subarray(25, 37));
  decipher.setAuthTag(data.subarray(37, 53));
  const files = JSON.parse(Buffer.concat([decipher.update(data.subarray(53)), decipher.final()]).toString());
  await mkdir(destination, { recursive: true });
  for (const name of names) await writeFile(join(destination, name), Buffer.from(files[name], 'base64'), { mode: 0o600 });
  await writeFile(join(destination, 'android-password.txt'), files.androidPassword, { mode: 0o600 });
}
