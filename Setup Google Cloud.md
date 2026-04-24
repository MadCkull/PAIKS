<div style="background-color: #f3f7f9; padding: 15px; border-radius: 12px; border: 1px solid #d0e1e8; margin-bottom: 20px;">
<strong>Context & Prerequisites:</strong> 
This guide configures a Google Cloud project to allow PAIKS to access your Google Drive. The configuration uses `http://127.0.0.1:8000` as the base address, which is the default port for the PAIKS Django server. 
</div>

## Step 1 - Create a Google Cloud Project

1. Navigate to the [Google Cloud Console](https://console.cloud.google.com).
2. Click the **Project Dropdown** in the top left corner.
3. Select **New Project**.
4. Enter a meaningful project name (e.g., `PAIKS`).
5. Click **Create**.
6. _Crucial:_ Verify that your newly created project is currently selected in the top-left dropdown before proceeding.

## Step 2 - Enable the Google Drive API

1. Navigate to the [API Library](https://console.cloud.google.com/apis/library).
2. In the search bar, type **Google Drive API** and select the result.
3. Click the **Enable** button.

## Step 3 - Configure the OAuth Consent Screen

1. Go to the [OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent) configuration page.
2. Under "User Type", select **External**, then click **Create**.
3. Fill in the required application information:
   - **App name:** `PAIKS`
   - **User support email:** _[Your Email Address]_
   - **Developer contact email:** _[Your Email Address]_
4. Click **Save and Continue**.
5. On the **Scopes** page, click **Add or Remove Scopes**.
6. Manually add the following scopes by pasting them into the manual entry field:
   - `https://www.googleapis.com/auth/drive.readonly`
   - `https://www.googleapis.com/auth/drive.metadata.readonly`
7. Click **Update**, then **Save and Continue**.

## Step 4 - Add Test Users

<div style="background-color: #fff4e5; padding: 15px; border-radius: 12px; border: 1px solid #ffe0b2; margin-bottom: 15px;">
<strong>Important Restriction:</strong> While your application is in "Testing" status, only the specific users added in this step can authorize the app. Any other account attempting to log in will receive an "Access Blocked: Authorization Error".
</div>

1. Still in the Consent Screen setup, proceed to the **Test users** section.
2. Click **+ Add Users**.
3. Enter the exact Gmail addresses of anyone who needs to test or use the application (including your own developer email).
4. Click **Save**.

## Step 5 - Create OAuth Credentials (`google_creds.json`)

1. Navigate to the [Credentials Dashboard](https://console.cloud.google.com/apis/credentials).
2. Click **+ Create Credentials** at the top, then select **OAuth client ID**.
3. Set the **Application type** to **Web application**.
4. Name the client (e.g., `PAIKS Local Client`).
5. Scroll down to **Authorized redirect URIs** and click **+ Add URI**.
6. Enter exactly: `http://127.0.0.1:8000/api/auth/callback`
7. Click **Create**.
8. A modal window will appear displaying your Client ID and Client Secret. Click **Download JSON**.
9. Rename the downloaded file strictly to **`google_creds.json`**.
10. Move this file into the following directory inside your project root:
    **`.storage/auth/google_creds.json`**

## Step 6 - Verification

Once the file is in place, restart the PAIKS launcher. You can then navigate to the **Source Configuration** in the PAIKS Settings to begin the one-time authorization process.
