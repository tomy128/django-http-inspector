from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.urls import path


def echo(request):
    return JsonResponse({"method": request.method, "body": request.body.decode("utf-8", "replace")})


def cookies(request):
    response = HttpResponse("cookies")
    response.set_cookie("one", "1")
    response.set_cookie("two", "2")
    return response


def stream(request):
    return StreamingHttpResponse(iter([b"first", b"second"]))


urlpatterns = [path("echo/", echo), path("cookies/", cookies), path("stream/", stream)]
