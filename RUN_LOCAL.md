# RUN_LOCAL.md - Chay Lab 04 Team Core

Huong dan nay dung de build container va chay lai Newman test tren service Core Business da dong goi Docker.

## 1. Cai dependency test

```bash
npm install
```

## 2. Build Docker image

```bash
docker build -t fit4110/team-core:lab04 .
```

## 3. Run container

```bash
docker run --rm --name fit4110-team-core-lab04 -p 8000:8000 --env-file .env.example fit4110/team-core:lab04
```

Kiem tra health o terminal khac:

```bash
curl http://localhost:8000/health
```

Ket qua mong doi:

```json
{
  "status": "ok",
  "service": "team-core",
  "time": "2026-06-06T00:00:00+00:00"
}
```

## 4. Chay Newman tren container

```bash
npm run test:local
```

Report sinh tai:

```text
reports/newman-lab04-local.xml
reports/newman-lab04-local.html
```

## 5. Lenh nhanh

```bash
make build
make run
make test-docker
make stop
```
