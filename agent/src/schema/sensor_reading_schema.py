from marshmallow import Schema, fields

from schema.sensor_object_schema import SensorObjectSchema


class SensorReadingSchema(Schema):
    sensor_object = fields.Nested(SensorObjectSchema)
    sensor_type = fields.Str()
    timestamp = fields.DateTime("iso")
    payload = fields.Dict(keys=fields.Str(), values=fields.Raw())
    source = fields.Str()
    quality = fields.Str()
