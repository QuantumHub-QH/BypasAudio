FROM python:3.12-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg nodejs npm \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
RUN pip install --no-cache-dir yt-dlp
COPY . .

ENV NODE_ENV=production
EXPOSE 3000
CMD ["npm", "start"]
