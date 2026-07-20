from pathlib import Path

from docker.errors import ImageNotFound

DEFAULT_IMAGE = "github-issue-triage:latest"


def ensure_image(docker_client, image_name: str = DEFAULT_IMAGE):
    try:
        return docker_client.images.get(image_name)
    except ImageNotFound:
        context = Path(__file__).resolve().parent
        image, _ = docker_client.images.build(path=str(context), dockerfile="Dockerfile", tag=image_name, rm=True)
        return image
