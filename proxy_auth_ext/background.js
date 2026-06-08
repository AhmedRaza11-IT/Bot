chrome.proxy.settings.set({
        value: {
            mode: "fixed_servers",
            rules: {
                singleProxy: { scheme: "http", host: "192.168.1.1", port: parseInt(8080) },
                bypassList: ["localhost", "127.0.0.1"]
            }
        }, 
        scope: "regular"
    }, function() {});

    chrome.webRequest.onAuthRequired.addListener(
        function callback(details) {
            return {
                authCredentials: { username: "user123", password: "pass456" }
            };
        },
        { urls: ["<all_urls>"] },
        ["asyncBlocking"]
    );