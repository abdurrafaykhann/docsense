FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5173
# Serve the production bundle: a handful of files instead of ~hundreds of unbundled dev modules
# (the dev server drops connections under Docker Desktop on Windows).
RUN npm run build
CMD ["npm", "run", "preview"]
