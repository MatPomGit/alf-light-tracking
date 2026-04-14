from g1_light_tracking.utils.qr_schema import parse_parcel_qr

def test_parse_payload_for_parcel_track():
    data = parse_parcel_qr("shipment_id=S1;pickup_zone=A;dropoff_zone=B;parcel_type=box;mass_kg=1.5")
    assert data["shipment_id"] == "S1"
    assert data["pickup_zone"] == "A"
    assert data["dropoff_zone"] == "B"
