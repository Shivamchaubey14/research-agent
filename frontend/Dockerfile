# Frontend tier — Vite dev server (matches the docker-compose dev workflow).
# A production build would add a `vite build` stage served by nginx; that lands
# with the Kubernetes manifests.
FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
