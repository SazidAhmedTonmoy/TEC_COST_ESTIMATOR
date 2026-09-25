import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath,URL} from 'node:url';
export default defineConfig({base:'/tenders/',plugins:[react()],resolve:{alias:{'@':fileURLToPath(new URL('./src',import.meta.url))}},build:{outDir:'../tenders_web',emptyOutDir:true,target:'es2022'},server:{proxy:{'/api':'http://127.0.0.1:8080'}}});
