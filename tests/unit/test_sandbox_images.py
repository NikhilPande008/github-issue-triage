import triage.sandbox.images as images


def test_existing_image_is_reused() -> None:
    image = object()

    class FakeImages:
        def get(self, name):
            return image

    class FakeClient:
        images = FakeImages()

    assert images.ensure_image(FakeClient(), "existing") is image
