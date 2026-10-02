import { mkdir, copyFile } from 'node:fs/promises';
await mkdir('public/swagger', { recursive: true });
for (const file of ['swagger-ui-bundle.js', 'swagger-ui.css', 'LICENSE', 'NOTICE']) {
  await copyFile(`node_modules/swagger-ui-dist/${file}`, `public/swagger/${file}`);
}
