FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev

COPY public ./public
COPY src ./src
COPY scripts ./scripts
COPY database ./database

ENV NODE_ENV=production
EXPOSE 3000
CMD ["node", "src/server.js"]
