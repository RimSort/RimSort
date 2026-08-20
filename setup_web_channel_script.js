const BadgeState = @badge_state_js@;
const PAGE_MODE = '@page_mode@';
const INJECT_DELAY_MS = @inject_delay_ms@;

const TILE_SELECTORS = ['.workshopItem', '[data-publishedfileid]'];

function rimsortBrowseTileFromLink(link) {
	const aspect = link.closest('.aspectratio_16x9');
	if (aspect) {
		const panel = aspect.closest('.Panel');
		if (panel) {
			return panel;
		}
	}
	return link.closest('.workshopItem')
		|| link.closest('[data-publishedfileid]')
		|| link.closest('.Panel');
}

function rimsortModTitleFromBrowseTile(tile, modId) {
	if (!tile) {
		return modId;
	}
	const legacyTitle = tile.querySelector('.workshopItemTitle');
	if (legacyTitle && legacyTitle.textContent.trim()) {
		return legacyTitle.textContent.trim();
	}
	const links = tile.querySelectorAll('a[href*="filedetails/?id="]');
	for (const link of links) {
		const text = link.textContent.trim();
		if (text) {
			return text;
		}
	}
	const img = tile.querySelector('img[alt]');
	if (img && img.alt) {
		return img.alt;
	}
	return modId;
}

function rimsortFindBrowseTitleElement(tile) {
	if (!tile) {
		return null;
	}
	const legacyTitle = tile.querySelector('.workshopItemTitle');
	if (legacyTitle) {
		return legacyTitle;
	}
	const links = tile.querySelectorAll('a[href*="filedetails/?id="]');
	for (const link of links) {
		if (link.textContent.trim()) {
			return link;
		}
	}
	return null;
}

function rimsortCollectBrowseModEntries() {
	const entries = [];
	const seenModIds = new Set();
	document.querySelectorAll('a[href*="filedetails/?id="]').forEach(function(link) {
		const match = link.href.match(/id=(\d+)/);
		if (!match) {
			return;
		}
		const modId = match[1];
		if (seenModIds.has(modId)) {
			return;
		}
		const tile = rimsortBrowseTileFromLink(link);
		if (!tile) {
			return;
		}
		seenModIds.add(modId);
		entries.push({ modId: modId, tile: tile });
	});
	return entries;
}

function rimsortModStatus(installedMods, addedMods, modId) {
	const installedSet = window._rimsortInstalledSet;
	const addedSet = window._rimsortAddedSet;
	if (installedSet && installedSet.has(modId)) {
		return BadgeState.INSTALLED;
	}
	if (addedSet && addedSet.has(modId)) {
		return BadgeState.ADDED;
	}
	if (installedMods.includes(modId)) {
		return BadgeState.INSTALLED;
	}
	if (addedMods.includes(modId)) {
		return BadgeState.ADDED;
	}
	return BadgeState.DEFAULT;
}

function findModTile(modId) {
	for (const selector of TILE_SELECTORS) {
		const tiles = document.querySelectorAll(selector);
		for (const tile of tiles) {
			const link = tile.querySelector(`a[href*="id=${modId}"]`);
			if (link) {
				return tile;
			}
		}
	}
	const directLink = document.querySelector(`a[href*="id=${modId}"]`);
	if (directLink) {
		return rimsortBrowseTileFromLink(directLink);
	}
	return null;
}

function rimsortFindQuickViewButtons() {
	return [...document.querySelectorAll(
		'div.Panel[role="button"] svg.SVGIcon_MagnifyingGlass'
	)].map(function(svg) {
		return svg.closest('div.Panel[role="button"]');
	}).filter(Boolean);
}

function rimsortModIdFromHubCard(quickViewEl) {
	let el = quickViewEl;
	for (let depth = 0; depth < 12 && el; depth++) {
		const link = el.querySelector('a[href*="filedetails/?id="]');
		if (link) {
			const match = link.href.match(/id=(\d+)/);
			if (match) {
				return match[1];
			}
		}
		el = el.parentElement;
	}
	return null;
}

function rimsortModTitleFromHubCard(quickViewEl, modId) {
	let el = quickViewEl;
	for (let depth = 0; depth < 12 && el; depth++) {
		const link = el.querySelector('a[href*="filedetails/?id="]');
		if (link) {
			return link.getAttribute('title') || link.textContent.trim() || modId;
		}
		el = el.parentElement;
	}
	return modId;
}

function rimsortApplyHubButtonState(btn, status) {
	btn.classList.remove('rimsort-hub-installed', 'rimsort-hub-added', 'rimsort-hub-default');
	if (status === BadgeState.INSTALLED) {
		btn.classList.add('rimsort-hub-installed');
		btn.title = 'Already installed';
		btn.textContent = '✓';
	} else if (status === BadgeState.ADDED) {
		btn.classList.add('rimsort-hub-added');
		btn.title = 'Preparing to download';
		btn.textContent = '-';
	} else {
		btn.classList.add('rimsort-hub-default');
		btn.title = 'Add to list';
		btn.textContent = 'Add to list';
	}
}

function rimsortHubCardRoot(quickViewEl) {
	let el = quickViewEl;
	for (let depth = 0; depth < 12 && el; depth++) {
		const link = el.querySelector('a[href*="filedetails/?id="]');
		if (link) {
			return el;
		}
		el = el.parentElement;
	}
	return null;
}

function rimsortFindHubAddButton(modId, quickViewEl) {
	const card = rimsortHubCardRoot(quickViewEl);
	if (!card) {
		return null;
	}
	return card.querySelector('.rimsort-hub-add-btn[data-mod-id="' + modId + '"]');
}

function rimsortFindHubAddButtonByModId(modId) {
	return document.querySelector('.rimsort-hub-add-btn[data-mod-id="' + modId + '"]');
}

function rimsortCleanupHubLegacyBadges(card) {
	if (!card) {
		return;
	}
	card.querySelectorAll('.rimsort-modstatus-badge').forEach(function(badge) {
		badge.remove();
	});
}

function rimsortSyncModListsFromSets() {
	if (window._rimsortInstalledSet) {
		window._rimsortInstalledMods = Array.from(window._rimsortInstalledSet);
	}
	if (window._rimsortAddedSet) {
		window._rimsortAddedMods = Array.from(window._rimsortAddedSet);
	}
}

function rimsortRecordModStatus(modId, status) {
	if (!window._rimsortInstalledSet) {
		window._rimsortInstalledSet = new Set(window._rimsortInstalledMods || []);
	}
	if (!window._rimsortAddedSet) {
		window._rimsortAddedSet = new Set(window._rimsortAddedMods || []);
	}
	if (status === BadgeState.INSTALLED) {
		window._rimsortInstalledSet.add(modId);
		window._rimsortAddedSet.delete(modId);
	} else if (status === BadgeState.ADDED) {
		window._rimsortAddedSet.add(modId);
	} else {
		window._rimsortAddedSet.delete(modId);
	}
	rimsortSyncModListsFromSets();
}

function rimsortUpdateHubAddButton(modId, status) {
	rimsortRecordModStatus(modId, status);

	const existingBtn = rimsortFindHubAddButtonByModId(modId);
	if (existingBtn) {
		rimsortApplyHubButtonState(existingBtn, status);
		const card = rimsortHubCardRoot(existingBtn);
		rimsortCleanupHubLegacyBadges(card);
		return;
	}

	if (typeof window.rimsortInjectHubAddButtons === 'function') {
		window.rimsortInjectHubAddButtons();
	}
}
window.rimsortUpdateHubAddButton = rimsortUpdateHubAddButton;

function rimsortCreateHubAddButton(modId, status, modTitleText) {
	const btn = document.createElement('div');
	btn.className = 'rimsort-hub-add-btn Panel';
	btn.setAttribute('role', 'button');
	btn.tabIndex = 0;
	btn.dataset.modId = modId;
	rimsortApplyHubButtonState(btn, status);

	btn.addEventListener('click', function() {
		if (!window.browserBridge) {
			return;
		}
		btn.classList.add('pressed');
		setTimeout(function() {
			btn.classList.remove('pressed');
		}, 150);

		if (btn.classList.contains('rimsort-hub-default')) {
			rimsortRecordModStatus(modId, BadgeState.ADDED);
			window.browserBridge.add_mod_from_js(modId, modTitleText);
		} else if (btn.classList.contains('rimsort-hub-added')) {
			rimsortRecordModStatus(modId, BadgeState.DEFAULT);
			window.browserBridge.remove_mod_from_js(modId);
		}
	});

	return btn;
}

function rimsortInjectHubAddButtons() {
	const installedMods = window._rimsortInstalledMods || [];
	const addedMods = window._rimsortAddedMods || [];
	const installedSet = window._rimsortInstalledSet || new Set(installedMods);
	const addedSet = window._rimsortAddedSet || new Set(addedMods);
	window._rimsortInstalledSet = installedSet;
	window._rimsortAddedSet = addedSet;

	for (const quickViewEl of rimsortFindQuickViewButtons()) {
		const modId = rimsortModIdFromHubCard(quickViewEl);
		if (!modId) {
			continue;
		}

		const card = rimsortHubCardRoot(quickViewEl);
		rimsortCleanupHubLegacyBadges(card);

		const status = rimsortModStatus(installedMods, addedMods, modId);
		const existingBtn = rimsortFindHubAddButton(modId, quickViewEl);
		if (existingBtn) {
			rimsortApplyHubButtonState(existingBtn, status);
			continue;
		}

		const modTitleText = rimsortModTitleFromHubCard(quickViewEl, modId);
		quickViewEl.insertAdjacentElement(
			'afterend',
			rimsortCreateHubAddButton(modId, status, modTitleText)
		);
	}
}
window.rimsortInjectHubAddButtons = rimsortInjectHubAddButtons;

function rimsortFindBadgeObserverRoot() {
	return document.querySelector('.workshopBrowseRow')
		|| document.querySelector('.workshopBrowseItems')
		|| document.querySelector('#BrowseResultContainer')
		|| document.querySelector('main')
		|| document.body
		|| null;
}

function rimsortMutationIsRimSort(mutation) {
	const target = mutation.target;
	if (target instanceof Element && target.closest('.rimsort-modstatus-badge, .rimsort-hub-add-btn')) {
		return true;
	}
	for (const node of mutation.addedNodes) {
		if (!(node instanceof Element)) {
			continue;
		}
		if (
			node.classList.contains('rimsort-modstatus-badge')
			|| node.classList.contains('rimsort-hub-add-btn')
			|| node.querySelector('.rimsort-modstatus-badge, .rimsort-hub-add-btn')
		) {
			return true;
		}
	}
	return false;
}

function rimsortSetupPageObserver(callback) {
	if (window._rimsortObserver) {
		return;
	}
	const root = rimsortFindBadgeObserverRoot();
	if (!root) {
		return;
	}

	let observerDebounce = null;
	window._rimsortObserver = new MutationObserver(function(mutations) {
		if (window._rimsortUpdatingBadges) {
			return;
		}
		if (mutations.every(rimsortMutationIsRimSort)) {
			return;
		}
		if (observerDebounce) {
			clearTimeout(observerDebounce);
		}
		observerDebounce = setTimeout(callback, 500);
	});
	window._rimsortObserver.observe(root, { childList: true, subtree: true });
}

function rimsortWaitForQWebChannel(callback, attempt) {
	if (attempt === undefined) {
		attempt = 0;
	}
	if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined' && qt.webChannelTransport) {
		callback();
		return;
	}
	if (attempt >= 20) {
		console.error("QWebChannel is not defined. Cannot setup bridge.");
		return;
	}
	setTimeout(function() {
		rimsortWaitForQWebChannel(callback, attempt + 1);
	}, 50);
}

function rimsortInstallHistoryUrlSync() {
	if (window._rimsortHistoryUrlSync) {
		return;
	}
	window._rimsortHistoryUrlSync = true;

	const notify = function() {
		if (!window.browserBridge || typeof window.browserBridge.on_url_changed !== 'function') {
			return;
		}
		window.browserBridge.on_url_changed(window.location.href);
	};

	const wrapHistory = function(methodName) {
		const original = history[methodName];
		if (typeof original !== 'function') {
			return;
		}
		history[methodName] = function() {
			const result = original.apply(this, arguments);
			notify();
			return result;
		};
	};

	wrapHistory('pushState');
	wrapHistory('replaceState');
	window.addEventListener('popstate', notify);
	notify();
}

function setupRimSortWorkshopBridge(installedMods, addedMods) {
	window._rimsortInstalledMods = installedMods;
	window._rimsortAddedMods = addedMods;
	window._rimsortInstalledSet = new Set(installedMods);
	window._rimsortAddedSet = new Set(addedMods);

	if (window._rimsortBridgeReady) {
		rimsortInstallHistoryUrlSync();
		if (PAGE_MODE === 'browse' && typeof window.updateAllModBadges === 'function') {
			window.updateAllModBadges();
		} else if (PAGE_MODE === 'hub') {
			window.rimsortInjectHubAddButtons();
		}
		return;
	}

	new QWebChannel(qt.webChannelTransport, function(channel) {
		window.browserBridge = channel.objects.browserBridge;
		window._rimsortBridgeReady = true;
		console.log("QWebChannel bridge to Python ready!");
		rimsortInstallHistoryUrlSync();

		window.updateModBadge = function(modId, status) {
			if (PAGE_MODE === 'hub') {
				rimsortUpdateHubAddButton(modId, status);
				return;
			}

			rimsortRecordModStatus(modId, status);

			const tile = findModTile(modId);
			if (!tile) {
				console.log(`Mod tile for ${modId} not found.`);
				return;
			}

			let modStatusBadge = tile.querySelector('.rimsort-modstatus-badge');

			if (!modStatusBadge) {
				modStatusBadge = document.createElement('div');
				modStatusBadge.className = 'rimsort-modstatus-badge';

				let modTitleContainer = null;
				const collectionItemParent = tile.parentElement;
				if (collectionItemParent && collectionItemParent.classList.contains('collectionItem')) {
					modTitleContainer = collectionItemParent.querySelector('.collectionItemDetails');
				} else {
					modTitleContainer = tile;
				}

				const modTitleText = rimsortModTitleFromBrowseTile(tile, modId);

				const tileMouseoverHandler = function() {
					tile.classList.add('rimsort-tile-hovered');
					if (modStatusBadge.classList.contains('rimsort-mod-default') && PAGE_MODE !== 'browse') {
						modStatusBadge.style.opacity = '1';
						modStatusBadge.style.visibility = 'visible';
					}
				};
				const tileMouseoutHandler = function() {
					tile.classList.remove('rimsort-tile-hovered');
					if (modStatusBadge.classList.contains('rimsort-mod-default') && PAGE_MODE !== 'browse') {
						modStatusBadge.style.opacity = '0';
						modStatusBadge.style.visibility = 'hidden';
					}
				};
				tile.addEventListener('mouseover', tileMouseoverHandler);
				tile.addEventListener('mouseout', tileMouseoutHandler);

				const badgeMouseoverHandler = function() {
					modStatusBadge.classList.add('rimsort-badge-hovered');
				};
				const badgeMouseoutHandler = function() {
					modStatusBadge.classList.remove('rimsort-badge-hovered');
				};
				modStatusBadge.addEventListener('mouseover', badgeMouseoverHandler);
				modStatusBadge.addEventListener('mouseout', badgeMouseoutHandler);

				const badgeClickHandler = function() {
					if (!window.browserBridge) {
						return;
					}

					modStatusBadge.classList.add('pressed');
					setTimeout(function() {
						modStatusBadge.classList.remove('pressed');
					}, 150);

					if (modStatusBadge.classList.contains('rimsort-mod-default')) {
						rimsortRecordModStatus(modId, BadgeState.ADDED);
						window.browserBridge.add_mod_from_js(modId, modTitleText);
					} else if (modStatusBadge.classList.contains('rimsort-mod-added')) {
						rimsortRecordModStatus(modId, BadgeState.DEFAULT);
						window.browserBridge.remove_mod_from_js(modId);
					}
				};

				modStatusBadge.addEventListener('click', badgeClickHandler);

				tile.style.position = 'relative';
				tile.appendChild(modStatusBadge);
			}

			if (status === BadgeState.INSTALLED) {
				modStatusBadge.title = 'Already installed';
				modStatusBadge.innerHTML = '✓';
				modStatusBadge.classList.remove('rimsort-mod-added', 'rimsort-mod-default');
				modStatusBadge.classList.add('rimsort-mod-installed');
				const modTitleElement = rimsortFindBrowseTitleElement(tile);
				if (modTitleElement) {
					modTitleElement.style.color = '#4CAF50';
				}
				modStatusBadge.style.opacity = '1';
				modStatusBadge.style.visibility = 'visible';
			} else if (status === BadgeState.ADDED) {
				modStatusBadge.title = 'Preparing to download';
				modStatusBadge.innerHTML = '-';
				modStatusBadge.classList.remove('rimsort-mod-installed', 'rimsort-mod-default');
				modStatusBadge.classList.add('rimsort-mod-added');
				const modTitleElement = rimsortFindBrowseTitleElement(tile);
				if (modTitleElement) {
					modTitleElement.style.color = '';
				}
				modStatusBadge.style.opacity = '1';
				modStatusBadge.style.visibility = 'visible';
			} else {
				modStatusBadge.title = 'Add to list';
				modStatusBadge.innerHTML = 'Add to list';
				modStatusBadge.classList.remove('rimsort-mod-installed', 'rimsort-mod-added');
				modStatusBadge.classList.add('rimsort-mod-default');
				const modTitleElement = rimsortFindBrowseTitleElement(tile);
				if (modTitleElement) {
					modTitleElement.style.color = '';
				}
				if (PAGE_MODE === 'browse' || tile.classList.contains('rimsort-tile-hovered')) {
					modStatusBadge.style.opacity = '1';
					modStatusBadge.style.visibility = 'visible';
				} else {
					modStatusBadge.style.opacity = '0';
					modStatusBadge.style.visibility = 'hidden';
				}
			}

			if (modStatusBadge.matches(':hover')) {
				modStatusBadge.classList.add('rimsort-badge-hovered');
			} else {
				modStatusBadge.classList.remove('rimsort-badge-hovered');
			}
		};

		window._rimsortUpdatingBadges = false;
		window.updateAllModBadges = function() {
			if (PAGE_MODE !== 'browse') {
				return;
			}
			if (window._rimsortUpdatingBadges) {
				return;
			}
			window._rimsortUpdatingBadges = true;
			try {
				const seenModIds = new Set();
				const installedSet = window._rimsortInstalledSet || new Set();
				const addedSet = window._rimsortAddedSet || new Set();

				rimsortCollectBrowseModEntries().forEach(function(entry) {
					if (seenModIds.has(entry.modId)) {
						return;
					}
					seenModIds.add(entry.modId);
					if (installedSet.has(entry.modId)) {
						window.updateModBadge(entry.modId, BadgeState.INSTALLED);
					} else if (addedSet.has(entry.modId)) {
						window.updateModBadge(entry.modId, BadgeState.ADDED);
					} else {
						window.updateModBadge(entry.modId, BadgeState.DEFAULT);
					}
				});

				for (const selector of TILE_SELECTORS) {
					const tiles = document.querySelectorAll(selector);
					tiles.forEach(function(tile) {
						const link = tile.querySelector('a[href*="id="]');
						if (!link) {
							return;
						}
						const match = link.href.match(/id=(\d+)/);
						if (!match) {
							return;
						}
						const modId = match[1];
						if (seenModIds.has(modId)) {
							return;
						}
						seenModIds.add(modId);

						if (installedSet.has(modId)) {
							window.updateModBadge(modId, BadgeState.INSTALLED);
						} else if (addedSet.has(modId)) {
							window.updateModBadge(modId, BadgeState.ADDED);
						} else {
							window.updateModBadge(modId, BadgeState.DEFAULT);
						}
					});
				}
			} finally {
				window._rimsortUpdatingBadges = false;
			}
		};

		if (PAGE_MODE === 'browse') {
			document.body.classList.add('rimsort-grid-page');
			window.updateAllModBadges();
			rimsortSetupPageObserver(function() {
				window.updateAllModBadges();
			});
		} else if (PAGE_MODE === 'hub') {
			window.rimsortInjectHubAddButtons();
			rimsortSetupPageObserver(function() {
				window.rimsortInjectHubAddButtons();
			});
		}
	});
}

function rimsortScheduleWorkshopSetup(installed, added) {
	const run = function() {
		rimsortWaitForQWebChannel(function() {
			setupRimSortWorkshopBridge(installed, added);
		});
	};
	const schedule = function() {
		if (INJECT_DELAY_MS <= 0) {
			run();
			return;
		}
		setTimeout(run, INJECT_DELAY_MS);
	};
	if (document.readyState === 'complete') {
		schedule();
	} else {
		window.addEventListener('load', schedule, { once: true });
	}
}

rimsortScheduleWorkshopSetup(@installed_mods@, @added_mods@);

if (!document.getElementById('rimsort-workshop-badge-style')) {
	const style = document.createElement('style');
	style.id = 'rimsort-workshop-badge-style';
	style.textContent = `
    .rimsort-modstatus-badge {
        position: absolute;
        top: 5px;
        right: 5px;
        color: white;
        width: auto;
        min-width: 32px;
        height: 32px;
        padding: 0 8px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 12px;
        box-shadow: 0 0 4px black;
        cursor: default;
        user-select: none;
        transition: transform 0.1s ease, box-shadow 0.1s ease, opacity 0.2s ease, visibility 0.2s ease;
    }

    .rimsort-modstatus-badge.rimsort-badge-hovered {
        transform: scale(1.05);
        box-shadow: 0 0 8px rgba(0,0,0,0.4);
    }

    .rimsort-modstatus-badge.pressed {
        transform: scale(0.9);
    }

    .rimsort-mod-installed {
        background-color: #4CAF50;
    }

    .rimsort-mod-added {
        background-color: #FFA500;
        cursor: pointer;
    }

    .rimsort-mod-default {
        background-color: #2196F3;
        cursor: pointer;
    }

    body.rimsort-grid-page .rimsort-mod-default {
        opacity: 1;
        visibility: visible;
    }

    .rimsort-mod-default:not(body.rimsort-grid-page .rimsort-mod-default) {
        opacity: 0;
        visibility: hidden;
    }

    .rimsort-hub-add-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 32px;
        height: 32px;
        padding: 0 10px;
        margin-left: 6px;
        margin-right: 6px;
        margin-bottom: 6px;
        border-radius: 6px;
        color: white;
        font-weight: bold;
        font-size: 12px;
        box-shadow: 0 0 4px black;
        user-select: none;
        cursor: default;
        transition: transform 0.1s ease, box-shadow 0.1s ease;
    }

    .rimsort-hub-add-btn.rimsort-hub-default,
    .rimsort-hub-add-btn.rimsort-hub-added {
        cursor: pointer;
    }

    .rimsort-hub-add-btn.rimsort-hub-installed {
        background-color: #4CAF50;
    }

    .rimsort-hub-add-btn.rimsort-hub-added {
        background-color: #FFA500;
    }

    .rimsort-hub-add-btn.rimsort-hub-default {
        background-color: #2196F3;
    }

    .rimsort-hub-add-btn.pressed {
        transform: scale(0.9);
    }
`;
	document.head.appendChild(style);
}
