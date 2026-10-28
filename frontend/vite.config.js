import {defineConfig} from 'vite';
const proxy={'/api/':{target:'http://127.0.0.1:8000',changeOrigin:false,ws:false}};
export default defineConfig({
  server:{host:'127.0.0.1',port:5173,strictPort:true,proxy},
  preview:{host:'127.0.0.1',port:4173,strictPort:true,proxy,headers:{
    'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    'Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Cache-Control':'no-store'}},
});
