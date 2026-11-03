from vshort import shapes

PROPS = ["the-nhan-vien", "may-quet", "bang-ten", "barie", "cua", "toa-nha", "phong", "chot-bao-ve", "ket-sat",
         "hom-thu", "kien-hang", "xe-giao-hang", "camera-an-ninh", "hang-rao", "cau-thang", "toa-nha-tang"]


def test_props_are_in_the_library_and_valid():
    for slug in PROPS:
        doc = shapes.find(slug, None)
        assert doc is not None, slug
        assert shapes.problems(doc, slug) == [], slug
    assert {s for s in PROPS if "hinge" in shapes.find(s, None)} == {"barie", "cua", "ket-sat"}
