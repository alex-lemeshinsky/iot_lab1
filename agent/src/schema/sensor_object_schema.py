from marshmallow import Schema, fields

from schema.gps_schema import GpsSchema


class SensorObjectSchema(Schema):
    object_id = fields.Str()
    object_type = fields.Str()
    name = fields.Str()
    gps = fields.Nested(GpsSchema)
    metadata = fields.Dict(keys=fields.Str(), values=fields.Raw())
