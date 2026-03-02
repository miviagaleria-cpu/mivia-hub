#!/usr/bin/env python3
"""
MenuOS Server - Servidor local para admin automático
Maneja guardado automático de menu-data.json y upload de imágenes/videos
"""

import http.server
import socketserver
import json
import os
import base64
import hashlib
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from io import BytesIO

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️  PIL no disponible - imágenes no serán optimizadas")
    print("   Instalá con: pip3 install Pillow --break-system-packages")

PORT = 8080

class MenuHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # Deshabilitar caché para todos los archivos estáticos
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()
    
    def optimize_image(self, image_data, max_width=1200, quality=85):
        """Optimiza imagen: resize y compresión"""
        if not PIL_AVAILABLE:
            return image_data
        
        try:
            img = Image.open(BytesIO(image_data))
            
            # Convertir RGBA a RGB si es necesario
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            
            # Resize si es muy grande
            if img.width > max_width:
                ratio = max_width / img.width
                new_height = int(img.height * ratio)
                img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
            
            # Guardar optimizado
            output = BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            return output.getvalue()
        except Exception as e:
            print(f"⚠️  Error optimizando imagen: {e}")
            return image_data
    
    def do_POST(self):
        """Manejar guardado y upload de archivos"""
        
        # UPLOAD DE IMÁGENES/VIDEOS
        if self.path == '/upload-media':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                
                file_data = data.get('file')  # base64
                file_type = data.get('type', 'product')  # product, category, carousel, restaurant
                filename = data.get('filename', 'media')
                is_video = data.get('isVideo', False)
                
                # Decodificar base64
                if ',' in file_data:
                    file_data = file_data.split(',')[1]
                
                binary_data = base64.b64decode(file_data)
                
                # Determinar carpeta
                folder_map = {
                    'product': 'images/products',
                    'category': 'images/categories',
                    'carousel': 'images/carousel',
                    'restaurant': 'images/restaurant'
                }
                folder = folder_map.get(file_type, 'images/misc')
                os.makedirs(folder, exist_ok=True)
                
                # Generar nombre único
                file_hash = hashlib.md5(binary_data).hexdigest()[:8]
                timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
                
                if is_video:
                    ext = os.path.splitext(filename)[1] or '.mp4'
                    final_filename = f"{file_type}-{timestamp}-{file_hash}{ext}"
                    final_data = binary_data
                else:
                    # Optimizar imagen
                    final_data = self.optimize_image(binary_data)
                    final_filename = f"{file_type}-{timestamp}-{file_hash}.jpg"
                
                filepath = os.path.join(folder, final_filename)
                
                # Guardar archivo
                with open(filepath, 'wb') as f:
                    f.write(final_data)
                
                # Respuesta
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                original_size = len(binary_data)
                final_size = len(final_data)
                savings = ((original_size - final_size) / original_size * 100) if original_size > 0 else 0
                
                response = {
                    'success': True,
                    'path': filepath,
                    'size': final_size,
                    'originalSize': original_size,
                    'savings': f'{savings:.1f}%'
                }
                self.wfile.write(json.dumps(response).encode())
                
                print(f"📸 Guardado: {filepath} ({final_size//1024}KB, ahorro: {savings:.1f}%)")
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': False, 'error': str(e)}
                self.wfile.write(json.dumps(response).encode())
                print(f"❌ Error subiendo archivo: {e}")
            return
        
        # GUARDADO DE MENU-DATA.JSON
        if self.path == '/save':
            try:
                # Leer contenido enviado
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                menu_data = json.loads(post_data.decode('utf-8'))
                
                # Guardar archivo principal
                with open('menu-data.json', 'w', encoding='utf-8') as f:
                    json.dump(menu_data, f, indent=2, ensure_ascii=False)
                
                # Crear backup con timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d-%H%M')
                backup_filename = f'backups/menu-data-{timestamp}.json'
                
                # Crear carpeta backups si no existe
                os.makedirs('backups', exist_ok=True)
                
                with open(backup_filename, 'w', encoding='utf-8') as f:
                    json.dump(menu_data, f, indent=2, ensure_ascii=False)
                
                # Respuesta exitosa
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                response = {
                    'success': True,
                    'message': f'✅ Guardado automáticamente',
                    'backup': backup_filename
                }
                self.wfile.write(json.dumps(response).encode())
                
                print(f"✅ Guardado: menu-data.json")
                print(f"💾 Backup: {backup_filename}")
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {'success': False, 'error': str(e)}
                self.wfile.write(json.dumps(response).encode())
                print(f"❌ Error: {e}")
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_OPTIONS(self):
        """Manejar preflight CORS"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

print("=" * 60)
print("🚀 MenuOS Server")
print("=" * 60)
print(f"📡 Servidor corriendo en: http://localhost:{PORT}")
print(f"🔧 Admin: http://localhost:{PORT}/admin.html")
print(f"📱 Menú: http://localhost:{PORT}/menu.html")
print("=" * 60)
print(f"📸 Optimización de imágenes: {'✅ Activa' if PIL_AVAILABLE else '⚠️  Desactivada'}")
print(f"🎬 Soporte de videos: ✅ Activo")
print("=" * 60)
print("💡 Presioná Ctrl+C para detener")
print("=" * 60)

with socketserver.TCPServer(("", PORT), MenuHandler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Servidor detenido")
