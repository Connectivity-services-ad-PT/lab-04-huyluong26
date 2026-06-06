import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Literal, Optional, Union
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import AnyUrl, BaseModel, Field


SERVICE_NAME = os.getenv("SERVICE_NAME", "team-core")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.0.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-token")


app = FastAPI(
    title="FIT4110 Lab 04 - Core Business Service",
    version=SERVICE_VERSION,
    description="Dockerized Core Business API aligned with the Lab 03 team-core contract.",
)


class Problem(BaseModel):
    type: str = "https://campus.local/errors/validation"
    title: str
    status: int = Field(..., ge=400, le=599)
    detail: Optional[str] = None
    instance: Optional[str] = None
    errors: List[Dict[str, str]] = []


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    time: str


class CreateAlertRequest(BaseModel):
    sourceService: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    alertType: Literal[
        "UNAUTHORIZED_ACCESS",
        "SENSOR_THRESHOLD_EXCEEDED",
        "UNKNOWN_PERSON",
        "SYSTEM_ERROR",
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    message: str = Field(..., min_length=5, max_length=500)
    relatedEventId: Optional[str] = None


class Alert(CreateAlertRequest):
    id: str
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"] = "OPEN"
    createdAt: str
    resolvedAt: Optional[str] = None


class SensorEvent(BaseModel):
    eventType: Literal["SENSOR_READING"]
    eventId: str
    deviceId: str = Field(..., pattern=r"^SENSOR-[0-9]{3}$")
    metric: Literal["temperature", "humidity", "smoke", "motion"]
    value: float = Field(..., ge=-100, le=1000)
    unit: str = Field(..., min_length=1, max_length=20)
    timestamp: str


class AccessEvent(BaseModel):
    eventType: Literal["ACCESS_CHECK"]
    eventId: str
    gateId: str = Field(..., pattern=r"^GATE-[0-9]{2}$")
    cardId: str = Field(..., pattern=r"^RFID-[0-9]{4}-[0-9]{3}$")
    decision: Literal["ALLOW", "DENY"]
    timestamp: str


class EventAccepted(BaseModel):
    eventId: str
    acceptedAt: str


class AccessCheckRequest(BaseModel):
    cardId: str = Field(..., pattern=r"^RFID-[0-9]{4}-[0-9]{3}$")
    gateId: str = Field(..., pattern=r"^GATE-[0-9]{2}$")
    timestamp: str
    faceMatched: Optional[bool] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class AccessCheckResponse(BaseModel):
    decision: Literal["ALLOW", "DENY"]
    expiresAt: str
    reasonCode: str


class FaceMatchRequest(BaseModel):
    imageRef: AnyUrl
    requestId: str
    cameraId: str
    timestamp: str


class FaceMatchResponse(BaseModel):
    detectionId: str
    detectionType: Literal["FACE"] = "FACE"
    faceMatched: bool
    isLive: bool
    confidence: float
    status: Literal["success", "low_confidence", "no_face_detected"]
    matchedPersonId: Optional[str] = None


ALERTS: List[Alert] = []
EVENTS: Dict[str, Union[SensorEvent, AccessEvent]] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def problem_response(
    *,
    status_code: int,
    title: str,
    detail: str,
    instance: str,
    problem_type: str = "https://campus.local/errors/validation",
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict:
    return {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": instance,
        "errors": errors or [],
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    content = exc.detail if isinstance(exc.detail, dict) else problem_response(
        status_code=exc.status_code,
        title=status.HTTP_STATUS_CODES.get(exc.status_code, "HTTP Error"),
        detail=str(exc.detail),
        instance=str(request.url.path),
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        media_type="application/problem+json",
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = []
    for item in exc.errors():
        field = ".".join(str(part) for part in item.get("loc", []))
        errors.append(
            {
                "field": field,
                "code": item.get("type", "validation_error"),
                "message": item.get("msg", "Invalid value"),
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=problem_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Du lieu khong hop le",
            detail="Payload hoac tham so request khong dung contract",
            instance=str(request.url.path),
            errors=errors,
        ),
        media_type="application/problem+json",
    )


def verify_bearer_token(authorization: Optional[str] = Header(default=None)) -> None:
    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=problem_response(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Chua xac thuc",
                detail="Thieu hoac sai Bearer token",
                instance="/",
                problem_type="https://campus.local/errors/unauthorized",
            ),
        )


@app.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    return HealthStatus(service=SERVICE_NAME, time=now_iso())


@app.head("/health")
def health_head() -> Response:
    return Response(status_code=status.HTTP_200_OK)


@app.post(
    "/alerts",
    response_model=Alert,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_bearer_token)],
    responses={400: {"model": Problem}, 401: {"model": Problem}, 422: {"model": Problem}},
)
def create_alert(payload: CreateAlertRequest, response: Response) -> Alert:
    alert = Alert(
        **payload.model_dump(),
        id=str(uuid4()),
        status="OPEN",
        createdAt=now_iso(),
        resolvedAt=None,
    )
    ALERTS.append(alert)
    response.headers["Location"] = f"/alerts/{alert.id}"
    return alert


@app.get("/alerts", dependencies=[Depends(verify_bearer_token)])
def list_alerts(
    cursor: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict:
    return {"items": ALERTS[:limit], "nextCursor": None, "hasMore": False}


@app.get("/alerts/recent", dependencies=[Depends(verify_bearer_token)])
def recent_alerts(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, List[Alert]]:
    return {"items": ALERTS[-limit:]}


@app.get("/alerts/{alert_id}", dependencies=[Depends(verify_bearer_token)])
def get_alert(alert_id: str) -> Alert:
    for alert in ALERTS:
        if alert.id == alert_id:
            return alert

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=problem_response(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Khong tim thay",
            detail=f"Alert {alert_id} khong ton tai",
            instance=f"/alerts/{alert_id}",
            problem_type="https://campus.local/errors/not-found",
        ),
    )


@app.post(
    "/events",
    response_model=EventAccepted,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_bearer_token)],
)
def create_event(payload: Union[SensorEvent, AccessEvent]) -> EventAccepted:
    if payload.eventId in EVENTS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=problem_response(
                status_code=status.HTTP_409_CONFLICT,
                title="Xung dot",
                detail="eventId da ton tai",
                instance="/events",
                problem_type="https://campus.local/errors/conflict",
            ),
        )

    EVENTS[payload.eventId] = payload
    return EventAccepted(eventId=payload.eventId, acceptedAt=now_iso())


@app.post(
    "/access/check",
    response_model=AccessCheckResponse,
    dependencies=[Depends(verify_bearer_token)],
)
def check_access(
    payload: AccessCheckRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> AccessCheckResponse:
    allowed = payload.cardId.endswith("001") and (payload.faceMatched is not False)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    return AccessCheckResponse(
        decision="ALLOW" if allowed else "DENY",
        expiresAt=expires_at.isoformat(timespec="seconds"),
        reasonCode="AUTHORIZED_CARD" if allowed else "ACCESS_DENIED",
    )


@app.post(
    "/vision/face-match",
    response_model=FaceMatchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_bearer_token)],
)
def request_face_match(payload: FaceMatchRequest) -> FaceMatchResponse:
    return FaceMatchResponse(
        detectionId=str(uuid4()),
        faceMatched=True,
        isLive=True,
        confidence=0.92,
        status="success",
        matchedPersonId="PERSON-1234",
    )
