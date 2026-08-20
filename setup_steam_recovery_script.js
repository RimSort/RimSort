(function() {
	if (window._rimsortSteamRecovery) {
		return;
	}
	window._rimsortSteamRecovery = true;

	function maybeReload(msg) {
		if (!msg || msg.indexOf('Failed to fetch dynamically imported module') < 0) {
			return;
		}
		if (sessionStorage.getItem('rimsort_steam_reload')) {
			return;
		}
		sessionStorage.setItem('rimsort_steam_reload', '1');
		location.reload();
	}

	window.addEventListener('unhandledrejection', function(event) {
		var message = event.reason && event.reason.message;
		maybeReload(message);
	});
})();
