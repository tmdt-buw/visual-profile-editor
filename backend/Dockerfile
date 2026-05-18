FROM node:22-slim AS frontend-build

WORKDIR /frontend

COPY visual-profile-editor/frontend/package.json visual-profile-editor/frontend/package-lock.json /frontend/
RUN npm ci

COPY visual-profile-editor/frontend /frontend
RUN npm run build

FROM python:3.12-slim

WORKDIR /app

COPY General-Ontology-Editor/pyproject.toml /general-ontology-editor/pyproject.toml
COPY General-Ontology-Editor/src /general-ontology-editor/src
COPY visual-profile-editor/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt && pip install --no-cache-dir -e /general-ontology-editor

COPY visual-profile-editor/backend/app /app/app
COPY visual-profile-editor/scripts /app/scripts
COPY visual-profile-editor/schemas /app/schemas
COPY visual-profile-editor/profiles /app/profiles
COPY visual-profile-editor/examples /app/examples
COPY --from=frontend-build /frontend/dist /app/frontend-dist
RUN chmod +x /app/scripts/generate.sh && mkdir -p /app/generated/jsonschema /app/generated/shacl

EXPOSE 8000
