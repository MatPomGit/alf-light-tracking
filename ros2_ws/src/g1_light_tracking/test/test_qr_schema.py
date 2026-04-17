from g1_light_tracking.utils.qr_schema import parse_parcel_qr

def test_parse_qr_semicolon():
    data = parse_parcel_qr("shipment_id=P1;pickup_zone=A1;dropoff_zone=B2;mass_kg=1.2")
    assert data["shipment_id"] == "P1"
    assert data["pickup_zone"] == "A1"
    assert data["dropoff_zone"] == "B2"
