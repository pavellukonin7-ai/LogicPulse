from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

ScopeItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]

class ServicePresentation(Input):
    scope_items: list[ScopeItem] = Field(default_factory=list, max_length=12)
    delivery_time: str = Field(default='', max_length=80)
    public_note: str = Field(default='', max_length=1000)
    button_text: str = Field(default='Обсудить проект', min_length=1, max_length=80)

class ServiceInput(ServicePresentation):
    slug: str = Field(min_length=2, max_length=80, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=20, max_length=1500)
    price_min: int = Field(ge=0, le=100000000, strict=True)
    price_max: int = Field(ge=0, le=100000000, strict=True)
    prices_approved: bool = False
    price_review_note: str = Field(default='', max_length=2000)
    active: bool = True

    @model_validator(mode='after')
    def check_prices(self):
        if self.price_max < self.price_min:
            raise ValueError('Максимальная цена должна быть не меньше минимальной.')
        if self.prices_approved and len(self.price_review_note) < 20:
            raise ValueError('Для публикации цен опишите согласованный объём, сроки и расчёт себестоимости.')
        return self

class ServiceAdmin(ServiceInput):
    model_config = ConfigDict(from_attributes=True)
    id: int

class ServicePublic(ServicePresentation):
    id: int
    slug: str
    name: str
    description: str
    currency: str = 'RUB'
    price_min: int | None = None
    price_max: int | None = None
    pricing_note: str = 'Стоимость после обсуждения задачи. AI, хостинг и сторонние сервисы рассчитываются отдельно.'

class RequestInput(Input):
    request_id: UUID
    service_id: int = Field(gt=0, strict=True)
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr = Field(max_length=254)
    company: str = Field(default='', max_length=160)
    message: str = Field(min_length=20, max_length=4000)
    consent: Literal[True]
    website: str = Field(default='', max_length=0, description='Антиспам-поле: должно оставаться пустым.')
    urgency: Literal['urgent', 'soon', 'research'] | None = None
    budget: int | None = Field(default=None, ge=0, le=100000000, strict=True)

class Receipt(BaseModel):
    id: str
    message: str = 'Заявка отправлена!'
