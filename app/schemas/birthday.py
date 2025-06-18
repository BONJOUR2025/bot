from pydantic import BaseModel


class BirthdayOut(BaseModel):
    id: str
    full_name: str
    birthdate: str
    age: int
    in_days: int
