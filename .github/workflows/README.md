<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

<h1 align="center">Workflows de Revisión de PR con Gemini</h1>

---

## Descripción de los Flujos

Este directorio contiene los workflows de GitHub Actions para la revisión automatizada de Pull Requests utilizando Google Gemini (`gemini-3.5-flash-lite`).

Existen dos flujos independientes que se activan según las rutas modificadas en los PRs hacia la rama `main`:

### 1. `PR-review-backend.yml`
- **Disparador**: Pull Request hacia `main` que incluya cambios en la carpeta `backend/**`.
- **Propósito**: Ejecuta la revisión de código específica para el backend (Python/FastAPI) utilizando el prompt configurado en `.gemini/commands/review-backend.toml`.

### 2. `PR-review-frontend.yml`
- **Disparador**: Pull Request hacia `main` que incluya cambios en la carpeta `frontend/**`.
- **Propósito**: Ejecuta la revisión de código específica para el frontend (React/Vite/TypeScript) utilizando el prompt configurado en `.gemini/commands/review-frontend.toml`.

---

## Configuración Requerida

Para que los workflows funcionen correctamente, se requiere configurar el siguiente Secret en el repositorio de GitHub (**Settings > Secrets and variables > Actions**):

- `GOOGLE_API_KEY`: Tu API Key de Google Gemini.

*(El `GITHUB_TOKEN` es inyectado automáticamente por GitHub Actions).*

---

## Cómo Probarlos

1. **Crear una rama de trabajo**:
   ```bash
   git checkout -b feature/prueba-review
   ```
2. **Modificar archivos**:
   - Para probar el backend: edita cualquier archivo dentro de `backend/`.
   - Para probar el frontend: edita cualquier archivo dentro de `frontend/`.
3. **Subir cambios y abrir Pull Request**:
   ```bash
   git add .
   git commit -m "test: verificar review de gemini"
   git push origin feature/prueba-review
   ```
4. **Verificar ejecución**:
   - Dirígete a la pestaña **Actions** en GitHub para ver el workflow en ejecución.
   - También puedes forzar o reintentar la revisión comentando en el PR:
     ```text
     @gemini-cli /review
     ```
