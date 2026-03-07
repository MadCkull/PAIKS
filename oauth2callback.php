<?php
/**
 * OAuth2 Callback Bridge
 * 
 * Google redirects here after user consent. This file forwards the
 * authorization code to the Flask API which handles the token exchange.
 */

$code  = isset($_GET['code'])  ? $_GET['code']  : '';
$state = isset($_GET['state']) ? $_GET['state'] : '';
$error = isset($_GET['error']) ? $_GET['error'] : '';

if ($error) {
    echo "<h2>Authorization Error</h2><p>" . htmlspecialchars($error) . "</p>";
    echo "<p><a href='http://127.0.0.1:8000/'>Return to Home</a></p>";
    exit;
}

if (empty($code)) {
    echo "<h2>Error</h2><p>No authorization code received.</p>";
    echo "<p><a href='http://127.0.0.1:8000/'>Return to Home</a></p>";
    exit;
}

// Forward the code to the Flask API callback
$flask_url = 'http://127.0.0.1:5001/auth/callback?code=' . urlencode($code);
if ($state) {
    $flask_url .= '&state=' . urlencode($state);
}

header('Location: ' . $flask_url);
exit;
?>
