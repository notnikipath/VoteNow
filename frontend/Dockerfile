FROM node:20-alpine AS builder
WORKDIR /app
COPY frontend/package.json ./package.json
RUN npm install
COPY frontend .
ARG VITE_API_GATEWAY_URL=http://localhost:32082
ENV VITE_API_GATEWAY_URL=$VITE_API_GATEWAY_URL
RUN npm run build

FROM python:3.11-alpine
WORKDIR /srv
COPY --from=builder /app/dist /srv
EXPOSE 5178
CMD ["python", "-m", "http.server", "5178", "--bind", "0.0.0.0", "-d", "/srv"]
