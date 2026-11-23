from desktop_app.cdp import ChromeController


def test_controller_supports_only_the_two_target_sites():
    assert ChromeController._supported_url("https://chatgpt.com/")
    assert ChromeController._supported_url("https://www.perplexity.ai/search")
    assert ChromeController._supported_url("https://perplexity.ai/")
    assert not ChromeController._supported_url("https://example.com/")
    assert not ChromeController._supported_url("http://chatgpt.com/")
    assert not ChromeController._supported_url("https://chatgpt.com.evil.example/")
