FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . ./
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
# 실제 서버가 붙기 전까지는 MSW 가짜 API를 켠다. 서버가 생기면 false로 빌드한다.
ARG VITE_USE_MOCK=true
ENV VITE_USE_MOCK=${VITE_USE_MOCK}
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
