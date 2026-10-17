<p align="center">
  <img src="https://github.com/synapse-ai-hub/sources/raw/main/logo_transparente.png" alt="Logo" width="150">
</p>

---

# Onboarding rápido

Bienvenido/a al proyecto `synapseForge`. Estos son los pasos mínimos para dejar tu entorno listo y comenzar a contribuir.

---

## 1. Clonar el repositorio

```bash
>>> git clone https://github.com/synapse-ai-hub/synapseForge.git
>>> cd synapseForge
```

---

## 2. Instalar dependencias

Requiere Python 3.12+ y Node.js 20+.

```bash
>>> python -m venv .synapseForge
>>> .\.synapseForge\Scripts\Activate.ps1
>>> pip install -r requirements.txt
>>> npm install --prefix frontend
```

Para levantar el backend y el frontend en desarrollo, con el venv activado:

```bash
>>> synapseForge run .
```

---

## 3. Comandos básicos Git

- Crear y cambiar a una rama:

```bash
git checkout -b feature/mi-nueva-feature
```

- Mantener tu rama actualizada (rebase recomendado):

```bash
git fetch origin
git rebase origin/main
```

- Subir la rama:

```bash
git push origin feature/mi-nueva-feature
```

- Hacer commits atómicos en español e imperativo, con prefijo de tipo:

```bash
git commit -m "Feat: agregar mi nueva funcionalidad"
git commit -m "Fix: corregir error en validación"
```

> Formato: `Fix:`, `Feat:`, `Chore:`, `Docs:`, `Refactor:`, `Update:` + mensaje en español e imperativo. Ver detalle en [GIT_WORKFLOW.md](./GIT_WORKFLOW.md).

---

## 4. Abrir Pull Request

Al abrir PR en GitHub, usar el template correspondiente según el tipo de cambio:

- **General**: `?template=general.md`
- **Feature**: `?template=feature.md`
- **Fix**: `?template=fix.md`

```bash
# Ejemplo: abrir PR con template de feature
https://github.com/synapse-ai-hub/synapseForge/compare/main...feature/mi-feature?template=feature.md
```

---

## 5. Recursos y ayuda

- Revisá [GIT_WORKFLOW.md](./GIT_WORKFLOW.md) para el flujo de trabajo.
- Revisá [CONTRIBUTING.md](./CONTRIBUTING.md) para las áreas donde contribuir y las normas del proyecto.
- Si tenés dudas, abrí un issue o consultá al equipo.

---

Autor: synapse.ai  
Última actualización: 2026-10-17

