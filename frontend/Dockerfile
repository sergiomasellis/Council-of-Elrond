FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json* bun.lock* ./
RUN npm install

COPY . .

# Empty VITE_API_URL so the frontend uses relative URLs (nginx proxies /api)
ENV VITE_API_URL=""
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod -R 755 /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
