<p align="center">
  <img src="../src/logo_empresa.png" alt="Logo" width="150">
</p>

---

# Onboarding rápido

Bienvenido/a al proyecto `<repo>nombre_repo</repo>`. Estos son los pasos mínimos para dejar tu entorno listo y comenzar a contribuir.

---

## 1. Clonar el repositorio

```bash
>>> git clone https://github.com/<owner>nombre_owner</owner>/<repo>nombre_repo</repo>.git
>>> cd <repo>nombre_repo</repo>
```

---

## 2. Instalar dependencias

```bash
>>> python -m venv .<repo>nombre_repo</repo>
>>> .\<repo>nombre_repo</repo>\Scripts\Activate.ps1
>>> pip install -r requirements.txt
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

> Formato: `Fix:`, `Feat:`, `Chore:`, `Docs:`, `Refactor:`, `Update:` + mensaje en español e imperativo. Ver detalle en [GIT_WORKFLOW.md](./OnBoarding/GIT_WORKFLOW.md).

---

## 4. Abrir Pull Request

Al abrir PR en GitHub, usar el template correspondiente según el tipo de cambio:

- **General**: `?template=general.md`
- **Feature**: `?template=feature.md`
- **Fix**: `?template=fix.md`

```bash
# Ejemplo: abrir PR con template de feature
https://github.com/<owner>nombre_owner</owner>/<repo>nombre_repo</repo>/compare/main...feature/mi-feature?template=feature.md
```

---

## 5. Recursos y ayuda

- Revisá [GIT_WORKFLOW.md](./OnBoarding/GIT_WORKFLOW.md) para el flujo de trabajo.
- Si tenés dudas, abrí un issue o consultá al equipo.

---

Autor: <empresa>nombre_empresa</empresa>  
Última actualización: 2025-10-13

