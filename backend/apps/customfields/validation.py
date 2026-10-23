"""Bounded, strict JSON values. Decimal values use strings to preserve precision."""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from django.core.validators import validate_email, URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from apps.accounts.models import User
from apps.organizations.models import OrganizationalUnit

KINDS = {
    "short_text": "Texto curto",
    "long_text": "Texto longo",
    "integer": "Número inteiro",
    "decimal": "Número decimal",
    "date": "Data",
    "datetime": "Data e hora",
    "single_select": "Seleção única",
    "multi_select": "Seleção múltipla",
    "boolean": "Booleano",
    "url": "URL",
    "email": "E-mail",
    "user": "Referência a usuário",
    "unit": "Referência a unidade",
}
TEXT = {"short_text", "long_text", "url", "email"}
NUMERIC = {"integer", "decimal"}


def invalid(message):
    raise ValidationError(message)


def decimal(value):
    if not isinstance(value, str) or len(value) > 40 or not re.fullmatch(r"-?\d+(\.\d+)?", value):
        invalid("Informe decimal como texto, sem expoente, com ponto decimal.")
    try:
        result = Decimal(value)
    except InvalidOperation:
        invalid("Decimal inválido.")
    if not result.is_finite() or len(result.as_tuple().digits) > 28:
        invalid("Decimal deve ter até 28 algarismos.")
    return result


def validate_value(field, value, unit=None, metadata=False, previous=None):
    kind = field["kind"]
    rules = field["rules"]
    if value is None or value == "" or value == []:
        if field["required"] and not metadata:
            invalid("Campo obrigatório.")
        return None
    if kind in TEXT:
        if not isinstance(value, str):
            invalid("Informe texto.")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            invalid("Texto Unicode inválido.")
        if "\x00" in value:
            invalid("Texto não aceita caractere nulo.")
        limit = {"short_text": 500, "long_text": 20000, "url": 2048, "email": 254}[kind]
        if not rules.get("min_length", 0) <= len(value) <= rules.get("max_length", limit):
            invalid("Comprimento fora dos limites configurados.")
        try:
            if kind == "email":
                validate_email(value)
            if kind == "url":
                URLValidator(schemes=["http", "https"])(value)
        except DjangoValidationError:
            invalid("Formato inválido.")
    elif kind in NUMERIC:
        if kind == "integer":
            if type(value) is not int or abs(value) > 9007199254740991:
                invalid("Informe inteiro até 9007199254740991, sem booleanos ou frações.")
            number = Decimal(value)
        else:
            number = decimal(value)
            if max(0, -number.as_tuple().exponent) > rules.get("decimal_places", 8):
                invalid("Casas decimais acima do permitido.")
        if "min" in rules and number < Decimal(str(rules["min"])):
            invalid("Valor abaixo do mínimo.")
        if "max" in rules and number > Decimal(str(rules["max"])):
            invalid("Valor acima do máximo.")
    elif kind in {"date", "datetime"}:
        if not isinstance(value, str) or len(value) > 40:
            invalid("Informe uma data ISO válida.")
        try:
            if kind == "date":
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError
                parsed = date.fromisoformat(value)
            else:
                if "T" not in value:
                    raise ValueError
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.utcoffset() is None:
                    invalid("Data e hora devem incluir fuso horário.")
            for key in ["min", "max"]:
                if key in rules:
                    bound = (
                        date.fromisoformat(rules[key])
                        if kind == "date"
                        else datetime.fromisoformat(rules[key].replace("Z", "+00:00"))
                    )
                    if (key == "min" and parsed < bound) or (key == "max" and parsed > bound):
                        invalid("Data fora do intervalo configurado.")
        except (ValueError, TypeError):
            invalid("Data inválida.")
    elif kind == "boolean":
        if type(value) is not bool:
            invalid("Informe verdadeiro ou falso.")
    elif kind in {"single_select", "multi_select"}:
        allowed = {o["value"] for o in field["options"]}
        if kind == "single_select":
            if not isinstance(value, str) or value not in allowed:
                invalid("Opção inválida.")
        elif (
            not isinstance(value, list)
            or len(value) > len(allowed)
            or any(not isinstance(v, str) or v not in allowed for v in value)
            or len(set(value)) != len(value)
        ):
            invalid("Selecione opções válidas, sem duplicatas.")
    elif kind in {"user", "unit"}:
        try:
            if not isinstance(value, str):
                raise ValueError
            value = str(uuid.UUID(value))
        except ValueError:
            invalid("Referência UUID inválida.")
        # Never configure fixed reference defaults shared across organizational scopes.
        if metadata:
            invalid("Referências não permitem valor padrão fixo.")
        if value == previous:
            return value  # Retain historical inactive references, never newly assign them.
        if unit is None or not unit.active:
            invalid("Selecione a unidade responsável primeiro.")
        if kind == "user":
            valid = User.objects.filter(pk=value, is_active=True, memberships__unit=unit).exists()
        else:
            valid = (
                value == str(unit.pk)
                and OrganizationalUnit.objects.filter(pk=value, active=True).exists()
            )
        if not valid:
            invalid("Referência indisponível na unidade responsável.")
    return value


def validate_metadata(data):
    kind = data["kind"]
    rules = data["rules"]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,49}", data["key"]):
        invalid({"key": "Use letra minúscula inicial, letras, números e sublinhado."})
    if not isinstance(rules, dict):
        invalid({"rules": "Informe objeto de regras."})
    allowed = (
        {"min_length", "max_length"}
        if kind in TEXT
        else {"min", "max"}
        if kind in NUMERIC | {"date", "datetime"}
        else set()
    )
    if kind == "decimal":
        allowed |= {"decimal_places"}
    if set(rules) - allowed:
        invalid({"rules": "Regra não permitida para este tipo."})
    for key, val in rules.items():
        if key in {"min_length", "max_length", "decimal_places"}:
            limit = (
                8
                if key == "decimal_places"
                else {"short_text": 500, "long_text": 20000, "url": 2048, "email": 254}.get(kind, 0)
            )
            if type(val) is not int or not 0 <= val <= limit:
                invalid({"rules": "Limite inválido."})
        elif kind in NUMERIC:
            if kind == "integer":
                if type(val) is not int or abs(val) > 9007199254740991:
                    invalid({"rules": "Limites inteiros inválidos."})
            else:
                decimal(val)
        else:
            if not isinstance(val, str) or not val:
                invalid({"rules": "Limite de data exige texto ISO."})
            probe = {**data, "required": False, "rules": {}}
            validate_value(probe, val, metadata=True)
    low, high = ("min_length", "max_length") if kind in TEXT else ("min", "max")
    if low in rules and high in rules:
        if kind in NUMERIC:
            inverted = Decimal(str(rules[low])) > Decimal(str(rules[high]))
        elif kind == "datetime":
            inverted = datetime.fromisoformat(
                rules[low].replace("Z", "+00:00")
            ) > datetime.fromisoformat(rules[high].replace("Z", "+00:00"))
        else:
            inverted = rules[low] > rules[high]
        if inverted:
            invalid({"rules": "Mínimo deve ser menor ou igual ao máximo."})
    options = data["options"]
    if not isinstance(options, list) or len(options) > 100:
        invalid({"options": "Até 100 opções."})
    if kind in {"single_select", "multi_select"}:
        if not options:
            invalid({"options": "Informe opções."})
        seen = set()
        for option in options:
            if (
                not isinstance(option, dict)
                or set(option) != {"value", "label"}
                or not isinstance(option["value"], str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", option["value"])
                or not isinstance(option["label"], str)
                or not option["label"].strip()
                or len(option["label"]) > 160
                or option["value"] in seen
            ):
                invalid({"options": "Opções exigem value único e label legível."})
            try:
                option["label"].encode("utf-8")
            except UnicodeEncodeError:
                invalid({"options": "Rótulo Unicode inválido."})
            if "\x00" in option["label"]:
                invalid({"options": "Rótulo não aceita caractere nulo."})
            seen.add(option["value"])
    elif options:
        invalid({"options": "Este tipo não aceita opções."})
    if data["default"] is not None:
        validate_value(data, data["default"], metadata=True)
    return data


def validate_values(form, values, unit, defaults=False, previous=None):
    if not isinstance(values, dict) or len(values) > 50:
        invalid({"custom_values": "Informe objeto com até 50 campos."})
    fields = form.fields if form else []
    allowed = {f["key"] for f in fields}
    if set(values) - allowed:
        invalid(
            {
                "custom_values": "Campos ausentes da versão do formulário: "
                + ", ".join(sorted(set(values) - allowed))
            }
        )
    result, errors = {}, {}
    for field in fields:
        key = field["key"]
        value = values.get(key, field["default"] if defaults else None)
        try:
            result[key] = validate_value(field, value, unit, previous=(previous or {}).get(key))
        except ValidationError as exc:
            errors[key] = exc.detail
    if errors:
        invalid({"custom_values": errors})
    return result
