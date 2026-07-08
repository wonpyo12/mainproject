package com.example.ui.viewmodel

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.network.*
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class Screen {
    SPLASH, LOGIN, SIGNUP, ONBOARDING, DASHBOARD, SHOPPING, PAYMENT, COMPLETION, SUPPORT
}

enum class TrackingState {
    FOLLOWING, PAUSED, LOST_TRACKING, DISCONNECTED
}

data class CartItem(
    val id: String,
    val name: String,
    val price: Int,
    val quantity: Int,
    val imageEmoji: String,
)

data class CartUiState(
    val currentScreen: Screen = Screen.SPLASH,
    // 유저 정보
    val userId: Int = 0,
    val userName: String = "",
    val token: String = "",
    // 로봇 정보
    val matchedCartId: String = "",
    val robotSerialNumber: String = "",
    val cartBattery: Int = 85,
    val trackingState: TrackingState = TrackingState.FOLLOWING,
    // QR
    val qrToken: String = "",
    // 쇼핑
    val shoppingList: List<CartItem> = emptyList(),
    // 구매 내역
    val orderHistory: List<OrderRecord> = emptyList(),
    val isHistoryLoading: Boolean = false,
    // UI 상태
    val isLoading: Boolean = false,
    val errorMessage: String = "",
    val latestVoiceGuidance: String = "",
)

class CartViewModel : ViewModel() {

    private val TAG = "CartViewModel"
    private val api = RetrofitClient.api
    private val gson = Gson()

    private val _uiState = MutableStateFlow(CartUiState())
    val uiState: StateFlow<CartUiState> = _uiState.asStateFlow()

    fun navigateTo(screen: Screen) {
        _uiState.value = _uiState.value.copy(currentScreen = screen, errorMessage = "")
    }

    // ──────────────────────────────────────────────────────
    // [파트 1] 로그인: POST /api/auth/login → JWT 저장
    // ──────────────────────────────────────────────────────
    fun login(email: String, password: String, firstTime: Boolean = false) {
        if (email.isBlank() || password.isBlank()) {
            _uiState.value = _uiState.value.copy(errorMessage = "이메일과 비밀번호를 입력해 주세요.")
            return
        }
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = "")
            try {
                val response = api.login(LoginRequest(email, password))
                if (response.success && response.token != null && response.user != null) {
                    _uiState.value = _uiState.value.copy(
                        // 회원가입 직후엔 온보딩 튜토리얼을 먼저 보여준다.
                        currentScreen = if (firstTime) Screen.ONBOARDING else Screen.DASHBOARD,
                        token = response.token,
                        userId = response.user.id,
                        userName = response.user.name,
                        isLoading = false,
                    )
                    // Socket.io 연결 + 이벤트 리스너 등록
                    SocketManager.connect(response.token)
                    setupSocketListeners()
                } else {
                    _uiState.value = _uiState.value.copy(
                        errorMessage = response.message,
                        isLoading = false,
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "login error", e)
                _uiState.value = _uiState.value.copy(
                    errorMessage = "서버에 연결할 수 없습니다. (${e.message})",
                    isLoading = false,
                )
            }
        }
    }

    // ──────────────────────────────────────────────────────
    // [파트 1] 회원가입: POST /api/auth/register
    // ──────────────────────────────────────────────────────
    fun signUp(name: String, phone: String, email: String, password: String) {
        if (name.isBlank() || email.isBlank() || password.isBlank()) {
            _uiState.value = _uiState.value.copy(errorMessage = "필수 항목을 모두 입력해 주세요.")
            return
        }
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = "")
            try {
                val response = api.register(RegisterRequest(email, password, name, phone))
                if (response.success) {
                    // 가입 성공 → 자동 로그인 → 온보딩 튜토리얼
                    login(email, password, firstTime = true)
                } else {
                    _uiState.value = _uiState.value.copy(
                        errorMessage = response.message,
                        isLoading = false,
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "signUp error", e)
                _uiState.value = _uiState.value.copy(
                    errorMessage = "서버에 연결할 수 없습니다.",
                    isLoading = false,
                )
            }
        }
    }

    // ──────────────────────────────────────────────────────
    // [파트 2] QR 생성: GET /api/auth/qr → Redis에 TTL 180초 저장
    // ──────────────────────────────────────────────────────
    fun generateQR() {
        val token = _uiState.value.token
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = "")
            try {
                val response = api.generateQR("Bearer $token")
                _uiState.value = _uiState.value.copy(
                    qrToken = response.qrToken,
                    isLoading = false,
                )
                showVoice("QR 코드가 생성됐어요. 카트 카메라에 비춰 주세요.")
            } catch (e: Exception) {
                Log.e(TAG, "generateQR error", e)
                _uiState.value = _uiState.value.copy(
                    errorMessage = "QR 생성에 실패했습니다.",
                    isLoading = false,
                )
            }
        }
    }

    // ──────────────────────────────────────────────────────
    // [파트 2 & 3] Socket.io 이벤트 리스너 등록
    // ──────────────────────────────────────────────────────
    private fun setupSocketListeners() {
        // robot:matched → 로봇 연결 완료, SHOPPING 화면으로 이동
        SocketManager.on("robot:matched") { args ->
            val json = args[0].toString()
            val event = gson.fromJson(json, RobotMatchedEvent::class.java)
            viewModelScope.launch(Dispatchers.Main) {
                _uiState.value = _uiState.value.copy(
                    currentScreen = Screen.SHOPPING,
                    robotSerialNumber = event.robotSerialNumber,
                    matchedCartId = event.robotSerialNumber,
                    trackingState = TrackingState.FOLLOWING,
                )
                showVoice("카트와 연결됐어요. 안전하게 따라갈게요.")
            }
        }

        // cart:updated → RFID 인식 결과를 실시간으로 장바구니에 반영
        SocketManager.on("cart:updated") { args ->
            val json = args[0].toString()
            val event = gson.fromJson(json, CartUpdatedEvent::class.java)
            val newList = event.items.map { item ->
                CartItem(
                    id = "RF%04d".format(item.productId),
                    name = item.name,
                    price = item.price,
                    quantity = item.qty,
                    imageEmoji = "🛒",
                )
            }
            viewModelScope.launch(Dispatchers.Main) {
                // 실제로 추가되었거나 수량이 증가한 상품 식별
                val addedItem = newList.find { new ->
                    val old = _uiState.value.shoppingList.find { it.id == new.id }
                    old == null || new.quantity > old.quantity
                }

                _uiState.value = _uiState.value.copy(shoppingList = newList)

                if (addedItem != null) {
                    showVoice("${addedItem.name} 이(가) 카트에 담겼어요.")
                }
            }
        }

        // cart:error → 재고 부족 등 실시간 경고 처리
        SocketManager.on("cart:error") { args ->
            val json = args[0].toString()
            val event = gson.fromJson(json, CartErrorEvent::class.java)
            viewModelScope.launch(Dispatchers.Main) {
                showVoice(event.message)
            }
        }
    }

    // ──────────────────────────────────────────────────────
    // [파트 4] 결제 완료: POST /api/orders/complete
    //  Redis 장바구니 → MySQL 영구 저장 → 로봇 복귀 명령
    // ──────────────────────────────────────────────────────
    fun completeOrder() {
        val token = _uiState.value.token
        val robotSerial = _uiState.value.robotSerialNumber
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = "")
            try {
                val response = api.completeOrder(
                    authHeader = "Bearer $token",
                    request = CompleteOrderRequest(robotSerial),
                )
                if (response.success) {
                    _uiState.value = _uiState.value.copy(
                        currentScreen = Screen.COMPLETION,
                        isLoading = false,
                    )
                } else {
                    // errorMessage 는 로그인/회원가입 화면에만 표시되므로,
                    // 쇼핑 화면에서도 보이는 VoiceToast 로 실패 사유를 알린다.
                    _uiState.value = _uiState.value.copy(isLoading = false)
                    showVoice(response.message)
                }
            } catch (e: Exception) {
                Log.e(TAG, "completeOrder error", e)
                _uiState.value = _uiState.value.copy(isLoading = false)
                showVoice("결제 처리 중 오류가 발생했습니다. 네트워크를 확인해 주세요.")
            }
        }
    }

    // ──────────────────────────────────────────────────────
    // 구매 내역: GET /api/orders/history
    // ──────────────────────────────────────────────────────
    fun fetchOrderHistory() {
        val token = _uiState.value.token
        if (token.isBlank()) return
        viewModelScope.launch {
            _uiState.value = _uiState.value.copy(isHistoryLoading = true)
            try {
                val response = api.getOrderHistory("Bearer $token")
                _uiState.value = _uiState.value.copy(
                    orderHistory = if (response.success) response.orders else emptyList(),
                    isHistoryLoading = false,
                )
            } catch (e: Exception) {
                Log.e(TAG, "fetchOrderHistory error", e)
                _uiState.value = _uiState.value.copy(isHistoryLoading = false)
                showVoice("구매 내역을 불러오지 못했어요.")
            }
        }
    }

    fun setTrackingState(state: TrackingState) {
        _uiState.value = _uiState.value.copy(trackingState = state)
        val msg = when (state) {
            TrackingState.FOLLOWING -> "자동 추종을 시작해요."
            TrackingState.PAUSED    -> "카트가 멈췄어요."
            else -> ""
        }
        if (msg.isNotEmpty()) showVoice(msg)

        // 로봇에 실제 정지(HALT)/재개(RESUME) 신호 전송
        when (state) {
            TrackingState.PAUSED    -> sendRobotCommand(stop = true)
            TrackingState.FOLLOWING -> sendRobotCommand(stop = false)
            else -> {}
        }
    }

    // ──────────────────────────────────────────────────────
    // [로봇] 정지/재개: POST /api/robot/stop · /api/robot/resume
    //   백엔드 → 라파 cmd_server(TCP 9998) → 터틀봇3
    // ──────────────────────────────────────────────────────
    private fun sendRobotCommand(stop: Boolean) {
        val token = _uiState.value.token
        val robotSerial = _uiState.value.robotSerialNumber
        if (token.isBlank() || robotSerial.isBlank()) return
        viewModelScope.launch {
            try {
                val request = RobotCommandRequest(robotSerial)
                val response = if (stop) {
                    api.stopRobot("Bearer $token", request)
                } else {
                    api.resumeRobot("Bearer $token", request)
                }
                if (!response.success) {
                    showVoice(response.message)
                }
            } catch (e: Exception) {
                Log.e(TAG, "sendRobotCommand(stop=$stop) error", e)
                showVoice(if (stop) "로봇 정지 신호 전송에 실패했어요." else "추종 재개 신호 전송에 실패했어요.")
            }
        }
    }

    fun removeItem(item: CartItem) {
        _uiState.value = _uiState.value.copy(
            shoppingList = _uiState.value.shoppingList.filter { it.id != item.id }
        )
    }

    fun formatPrice(price: Int): String = "%,d원".format(price)

    fun logout() {
        SocketManager.disconnect()
        _uiState.value = CartUiState()
        navigateTo(Screen.LOGIN)
    }

    private fun showVoice(message: String) {
        _uiState.value = _uiState.value.copy(latestVoiceGuidance = message)
        viewModelScope.launch {
            delay(3500)
            if (_uiState.value.latestVoiceGuidance == message) {
                _uiState.value = _uiState.value.copy(latestVoiceGuidance = "")
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        SocketManager.disconnect()
    }
}

data class CartErrorEvent(
    val message: String
)
