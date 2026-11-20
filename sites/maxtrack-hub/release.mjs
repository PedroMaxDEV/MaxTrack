import { createHash, createPrivateKey, createPublicKey, generateKeyPairSync, sign, verify } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { copyFile, mkdir, readFile, stat, writeFile } from 'node:fs/promises';
import { basename, dirname, resolve } from 'node:path';

const [command, ...args] = process.argv.slice(2);

function storefront(origin) {
  const url = new URL(origin);
  if (url.protocol !== 'https:' || url.username || url.password ||
      url.pathname !== '/' || url.search || url.hash) {
    throw new Error('Use somente a origem HTTPS do Firebase, por exemplo https://seu-projeto.web.app');
  }
  return url.origin;
}

function releaseVersion(version) {
  if (!/^(0|[1-9][0-9]{0,3})(\.(0|[1-9][0-9]{0,3})){2}$/.test(version || '')) {
    throw new Error('Use uma versão no formato 0.4.0.');
  }
  return version;
}

async function sha256(file) {
  const digest = createHash('sha256');
  for await (const chunk of createReadStream(file)) digest.update(chunk);
  return digest.digest('hex');
}

function publicConfig(key) {
  const jwk = createPublicKey(key).export({ format: 'jwk' });
  const n = Buffer.from(jwk.n, 'base64url').toString('hex');
  const e = Number.parseInt(Buffer.from(jwk.e, 'base64url').toString('hex'), 16);
  if (n.length !== 512 || e !== 65537) throw new Error('A chave deve ser RSA-2048 com expoente 65537.');
  return { n, e };
}

async function signingKey(file) {
  return createPrivateKey(await readFile(file));
}

if (command === 'keygen' && args.length === 1) {
  const [file] = args;
  const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  await writeFile(file, privateKey.export({ type: 'pkcs8', format: 'pem' }), { flag: 'wx', mode: 0o600 });
  console.log('Chave criada. Guarde uma cópia em local privado.');
} else if (command === 'public' && args.length === 2) {
  const [keyFile, output] = args;
  const key = createPublicKey(await signingKey(keyFile));
  await writeFile(output, key.export({ type: 'spki', format: 'pem' }), { flag: 'wx' });
} else if (command === 'config' && args.length === 5) {
  const [keyFile, licensePublicFile, origin, version, output] = args;
  const config = {
    origin: storefront(origin), version: releaseVersion(version),
    updateKey: publicConfig(await signingKey(keyFile)),
    licenseKey: publicConfig(await readFile(licensePublicFile)),
  };
  if (config.updateKey.n === config.licenseKey.n) throw new Error('Use chaves separadas para atualização e ativação.');
  await mkdir(dirname(resolve(output)), { recursive: true });
  await writeFile(output, JSON.stringify(config) + '\n');
} else if (command === 'stage' && args.length === 5) {
  const [keyFile, configPath, exe, apk, target] = args;
  const key = await signingKey(keyFile);
  const config = JSON.parse(await readFile(configPath, 'utf8'));
  const version = releaseVersion(config.version);
  const expected = publicConfig(key);
  if (config.updateKey?.n !== expected.n || config.updateKey?.e !== expected.e) {
    throw new Error('A chave de assinatura não corresponde à chave pública embutida no Hub.');
  }
  storefront(config.origin);
  if (basename(exe) !== 'MaxHub-Setup.exe' || basename(apk) !== 'MaxGPS-Android.apk') {
    throw new Error('Use MaxHub-Setup.exe e MaxGPS-Android.apk.');
  }
  const size = (await stat(exe)).size;
  const checksum = await sha256(exe);
  const apkBytes = await readFile(apk);
  if (size < 1024 || apkBytes[0] !== 0x50 || apkBytes[1] !== 0x4b) throw new Error('Pacote de release inválido.');
  const localPath = `downloads/releases/${version}/MaxHub-Setup.exe`;
  const manifest = Buffer.from(JSON.stringify({ version, path: '/' + localPath, sha256: checksum, size }) + '\n');
  const signature = sign('sha256', manifest, key);
  if (!verify('sha256', manifest, createPublicKey(key), signature)) throw new Error('A assinatura do manifesto falhou.');
  const installer = resolve(target, 'public', localPath);
  const privateApk = resolve(target, 'functions/private/MaxGPS-Android.apk');
  await mkdir(dirname(installer), { recursive: true });
  await mkdir(dirname(privateApk), { recursive: true });
  try {
    const existing = await sha256(installer);
    if (existing !== checksum) throw new Error('Já existe um instalador diferente com esta versão. Aumente a versão.');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    await copyFile(exe, installer);
  }
  await copyFile(apk, privateApk);
  await writeFile(resolve(target, 'public/downloads/update.sig'), signature.toString('base64') + '\n');
  await writeFile(resolve(target, 'public/downloads/update.json'), manifest);
  console.log(`Release ${version} preparada em ${resolve(target)}.`);
} else {
  console.error('Uso: node release.mjs keygen <chave.pem> | public <chave.pem> <publica.pem> | config <chave-update.pem> <licenca-publica.pem> <origem> <versão> <config.json> | stage <chave-update.pem> <config.json> <MaxHub-Setup.exe> <MaxGPS-Android.apk> <destino>');
  process.exitCode = 1;
}
