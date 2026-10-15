"""
Tests for the donations feature: Ko-fi link, Bitcoin address, /support/.

The guarantees under test:
  - the configured Bitcoin address is a valid mainnet bc1q address and the
    configured signature proves it (so a copy-paste slip cannot ship);
  - an address that is invalid, unsigned, or not named in the signed message
    is never rendered anywhere (fail closed);
  - the QR code is generated from the same verified constant as the text;
  - no third-party code is added to any page, and the CSP is unchanged.
"""

import re

import pytest
from django.conf import settings
from django.urls import reverse

from libraries import donations
from bookworm.middleware import SecurityHeadersMiddleware


ADDRESS = "bc1qvj8qt5h5gnvfm4s2ypcqa0fy9vrsstyzx3zjl5"

# BIP173 test vector: valid mainnet P2WPKH, but not ours and not signed.
OTHER_VALID_ADDRESS = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"


@pytest.fixture(autouse=True)
def clear_donation_caches():
    donations._verified_address.cache_clear()
    donations.bitcoin_qr_svg.cache_clear()
    yield
    donations._verified_address.cache_clear()
    donations.bitcoin_qr_svg.cache_clear()


# =============================================================================
# Address validation (BIP173 / BIP350 vectors)
# =============================================================================

class TestAddressValidation:

    @pytest.mark.parametrize("address", [
        "BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4",
        "bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3",
        "bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7kt5nd6y",
        "tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sl5k7",
    ])
    def test_spec_valid_addresses_decode(self, address):
        assert donations.decode_segwit_address(address) is not None

    @pytest.mark.parametrize("address", [
        "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5",  # bad checksum
        "BC1QR508D6QEJXTDG4Y5R3ZARVARYV98GJ9P",  # bad program length
        "bc1zw508d6qejxtdg4y5r3zarvaryvqyzf3du",  # v2 with bech32 (needs bech32m)
        "bc1qW508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",  # mixed case
        "",
        None,
    ])
    def test_spec_invalid_addresses_rejected(self, address):
        assert donations.decode_segwit_address(address) is None

    def test_donation_address_must_be_mainnet_p2wpkh(self):
        assert donations.is_valid_donation_address(ADDRESS)
        # testnet, P2WSH, taproot, upper case: all valid Bitcoin, all wrong here
        assert not donations.is_valid_donation_address(
            "tb1qw508d6qejxtdg4y5r3zarvary0c5xw7kxpjzsx")
        assert not donations.is_valid_donation_address(
            "bc1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3")
        assert not donations.is_valid_donation_address(
            "bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7kt5nd6y")
        assert not donations.is_valid_donation_address(ADDRESS.upper())

    def test_single_character_typo_is_caught(self):
        typo = ADDRESS[:-1] + ("6" if ADDRESS[-1] != "6" else "7")
        assert not donations.is_valid_donation_address(typo)


# =============================================================================
# The configured constants
# =============================================================================

class TestConfiguredDonationSettings:

    def test_kofi_url_is_https_kofi(self):
        assert settings.KOFI_URL.startswith("https://ko-fi.com/")

    def test_configured_address_is_valid(self):
        assert donations.is_valid_donation_address(settings.BITCOIN_ADDRESS)

    def test_signed_message_names_the_address(self):
        assert settings.BITCOIN_ADDRESS in settings.BITCOIN_SIGNED_MESSAGE

    def test_signed_message_is_a_single_line(self):
        # Verification is byte-exact; a stray newline would break it for
        # anyone copying the message from the page.
        assert "\n" not in settings.BITCOIN_SIGNED_MESSAGE
        assert settings.BITCOIN_SIGNED_MESSAGE == settings.BITCOIN_SIGNED_MESSAGE.strip()

    def test_configured_signature_verifies(self):
        assert donations.verify_message_signature(
            settings.BITCOIN_ADDRESS,
            settings.BITCOIN_SIGNED_MESSAGE,
            settings.BITCOIN_SIGNATURE,
        )

    def test_configured_address_is_the_one_displayed(self):
        assert donations.bitcoin_address() == settings.BITCOIN_ADDRESS


class TestSignatureVerification:

    def test_altered_message_fails(self):
        assert not donations.verify_message_signature(
            settings.BITCOIN_ADDRESS,
            settings.BITCOIN_SIGNED_MESSAGE.replace("2026", "2025"),
            settings.BITCOIN_SIGNATURE,
        )

    def test_signature_does_not_transfer_to_another_address(self):
        message = settings.BITCOIN_SIGNED_MESSAGE.replace(ADDRESS, OTHER_VALID_ADDRESS)
        assert not donations.verify_message_signature(
            OTHER_VALID_ADDRESS, message, settings.BITCOIN_SIGNATURE)

    @pytest.mark.parametrize("signature", ["", "not base64!", "AAAA", "A" * 88])
    def test_malformed_signature_fails(self, signature):
        assert not donations.verify_message_signature(
            settings.BITCOIN_ADDRESS, settings.BITCOIN_SIGNED_MESSAGE, signature)


# =============================================================================
# Fail closed: an unproven address is never shown
# =============================================================================

class TestFailClosed:

    def test_empty_address_hides_bitcoin(self, settings):
        settings.BITCOIN_ADDRESS = ""
        assert donations.bitcoin_address() == ""

    def test_invalid_address_hides_bitcoin(self, settings):
        settings.BITCOIN_ADDRESS = ADDRESS[:-1] + "6"
        assert donations.bitcoin_address() == ""

    def test_swapped_address_without_new_signature_hides_bitcoin(self, settings):
        # The substitution attack: address changed, message and signature not.
        settings.BITCOIN_ADDRESS = OTHER_VALID_ADDRESS
        assert donations.bitcoin_address() == ""

    def test_swapped_address_and_message_without_signature_hides_bitcoin(self, settings):
        settings.BITCOIN_ADDRESS = OTHER_VALID_ADDRESS
        settings.BITCOIN_SIGNED_MESSAGE = settings.BITCOIN_SIGNED_MESSAGE.replace(
            ADDRESS, OTHER_VALID_ADDRESS)
        assert donations.bitcoin_address() == ""


# =============================================================================
# /support/ page
# =============================================================================

@pytest.mark.django_db
class TestSupportPage:

    def test_renders_with_kofi_and_bitcoin(self, client):
        response = client.get(reverse("libraries:support"))
        assert response.status_code == 200
        html = response.content.decode()
        assert f'href="{settings.KOFI_URL}"' in html
        assert 'id="bitcoin"' in html
        assert f'data-copy="{ADDRESS}"' in html
        assert f'href="bitcoin:{ADDRESS}"' in html
        assert settings.BITCOIN_SIGNATURE in html
        assert settings.BITCOIN_SIGNED_MESSAGE in html

    def test_grouped_address_reassembles_exactly(self, client):
        html = client.get(reverse("libraries:support")).content.decode()
        block = re.search(r'<div class="btc-address" id="btc-address">(.*?)</div>', html, re.S)
        assert block, "address block missing"
        text = re.sub(r"<[^>]+>", "", block.group(1))
        # No whitespace between groups: a selected copy is the exact address.
        assert text == ADDRESS

    def test_qr_is_built_from_the_verified_address(self, client):
        html = client.get(reverse("libraries:support")).content.decode()
        assert donations.bitcoin_qr_svg(ADDRESS) in html
        assert "<svg" in html and 'class="btc-qr"' in html

    def test_no_bitcoin_section_when_address_unproven(self, client, settings):
        settings.BITCOIN_ADDRESS = OTHER_VALID_ADDRESS
        html = client.get(reverse("libraries:support")).content.decode()
        assert 'id="bitcoin"' not in html
        assert OTHER_VALID_ADDRESS not in html
        assert "<svg" not in html
        # Ko-fi still offered
        assert f'href="{settings.KOFI_URL}"' in html

    def test_no_kofi_section_when_url_empty(self, client, settings):
        settings.KOFI_URL = ""
        html = client.get(reverse("libraries:support")).content.decode()
        assert 'class="btn-kofi"' not in html
        assert 'id="bitcoin"' in html

    def test_in_sitemap(self, client):
        assert b"/support/" in client.get("/sitemap.xml").content


# =============================================================================
# Placement: footers, map navbar, detail page
# =============================================================================

BTC_LINK = '/support/#bitcoin'


@pytest.mark.django_db
class TestPlacement:

    def test_landing_footer(self, client):
        html = client.get(reverse("libraries:landing")).content.decode()
        footer = html[html.index('<footer class="landing-footer">'):]
        assert settings.KOFI_URL in footer
        assert BTC_LINK in footer
        assert 'aria-label="Donate with Bitcoin"' in footer

    def test_walk_footer(self, client):
        html = client.get(reverse("libraries:library_walk")).content.decode()
        footer = html[html.index('<footer class="walk-footer">'):]
        assert settings.KOFI_URL in footer
        assert BTC_LINK in footer

    def test_map_navbar_has_support_not_add_library(self, client):
        html = client.get(reverse("libraries:map")).content.decode()
        nav = html[html.index('<nav class="navbar'):html.index('</nav>')]
        assert settings.KOFI_URL in nav
        assert BTC_LINK in nav
        assert "btn-add-library" not in html
        # Adding a library is still possible from the map controls.
        assert 'aria-label="Add a library"' in html

    def test_support_never_inside_map_surface(self, client):
        html = client.get(reverse("libraries:map")).content.decode()
        legend = html[html.index('<details class="map-legend"'):html.index('</details>')]
        controls = html[html.index('<div class="map-controls">'):html.index('<details class="map-legend"')]
        for surface in (legend, controls):
            assert "ko-fi" not in surface
            assert BTC_LINK not in surface

    def test_detail_page_support_line(self, client, verified_library):
        html = client.get(verified_library.get_absolute_url()).content.decode()
        assert 'class="detail-support"' in html
        assert BTC_LINK in html

    def test_bitcoin_links_vanish_when_unproven(self, client, settings):
        settings.BITCOIN_ADDRESS = OTHER_VALID_ADDRESS
        for name in ("landing", "map", "library_walk", "support"):
            html = client.get(reverse(f"libraries:{name}")).content.decode()
            assert BTC_LINK not in html, name
            assert "bi-currency-bitcoin" not in html, name


# =============================================================================
# No third-party code, CSP unchanged
# =============================================================================

ALLOWED_SCRIPT_HOSTS = {"cdn.jsdelivr.net", "unpkg.com"}


@pytest.mark.django_db
class TestNoThirdPartyCode:

    @pytest.mark.parametrize("name", ["landing", "map", "library_walk", "support"])
    def test_no_new_external_scripts_or_frames(self, client, name):
        html = client.get(reverse(f"libraries:{name}")).content.decode()
        hosts = set(re.findall(r'<script[^>]+src="https?://([^/"]+)', html))
        assert hosts <= ALLOWED_SCRIPT_HOSTS, hosts
        assert "<iframe" not in html
        assert "storage.ko-fi.com" not in html
        assert "ko-fi.com/widgets" not in html

    def test_support_page_loads_no_scripts_at_all_except_inline(self, client):
        html = client.get(reverse("libraries:support")).content.decode()
        assert not re.search(r'<script[^>]+src=', html)

    def test_csp_has_no_kofi_or_new_hosts(self, client):
        response = client.get(reverse("libraries:support"))
        csp = response["Content-Security-Policy"]
        assert csp == SecurityHeadersMiddleware(lambda r: None).build_csp()
        assert "ko-fi" not in csp
        assert "frame-ancestors 'none'" in csp
