//! 셸이 웹뷰로 돌려주는 오류.
//!
//! `#[tauri::command]` 의 실패 값은 `Serialize` 여야 프론트엔드의 `invoke`
//! reject 값으로 도착한다. 그래서 오류마다 기계가 읽는 `code` 와 사람이 읽는
//! `message` 을 함께 실어 보낸다. 프론트엔드는 `code` 로 분기하고 `message`
//! 를 그대로 토스트에 쓰면 된다.

use serde::{Serialize, Serializer};

/// 프론트엔드가 받는 오류 페이로드.
#[derive(Debug, Clone, Serialize)]
pub struct ErrorPayload {
    /// 기계가 읽는 분류. `invalid_url`, `unsupported_scheme`, …
    pub code: &'static str,
    /// 사람이 읽는 설명(한국어).
    pub message: String,
}

/// 셸이 만들 수 있는 모든 오류.
#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("외부 링크 주소가 올바르지 않습니다: {0}")]
    InvalidUrl(String),

    #[error("http/https 가 아닌 주소는 열 수 없습니다 ({0})")]
    UnsupportedScheme(String),

    #[error("알림을 표시하지 못했습니다: {0}")]
    Notification(String),

    #[error("창 테마를 바꾸지 못했습니다: {0}")]
    Theme(String),

    #[error("API 서버에 연결하지 못했습니다: {0}")]
    Api(String),

    #[error("파일을 저장하지 못했습니다: {0}")]
    File(String),

    #[error("내부 오류가 발생했습니다: {0}")]
    Internal(String),
}

impl Error {
    /// 기계가 읽는 오류 분류.
    pub fn code(&self) -> &'static str {
        match self {
            Error::InvalidUrl(_) => "invalid_url",
            Error::UnsupportedScheme(_) => "unsupported_scheme",
            Error::Notification(_) => "notification_failed",
            Error::Theme(_) => "theme_failed",
            Error::Api(_) => "api_error",
            Error::File(_) => "file_write_failed",
            Error::Internal(_) => "internal",
        }
    }

    /// 직렬화할 페이로드를 만든다.
    pub fn payload(&self) -> ErrorPayload {
        ErrorPayload {
            code: self.code(),
            message: self.to_string(),
        }
    }
}

impl Serialize for Error {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        self.payload().serialize(serializer)
    }
}

impl From<crate::api::ApiError> for Error {
    fn from(err: crate::api::ApiError) -> Self {
        Error::Api(err.to_string())
    }
}
