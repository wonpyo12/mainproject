package com.example.ui.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

enum class Screen {
    SPLASH, LOGIN, SIGNUP, DASHBOARD, SHOPPING, PAYMENT, COMPLETION
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
    val userName: String = "",
    val matchedCartId: String = "",
    val cartBattery: Int = 85,
    val trackingState: TrackingState = TrackingState.FOLLOWING,
    val shoppingList: List<CartItem> = emptyList(),
    val latestVoiceGuidance: String = "",
)

class CartViewModel : ViewModel() {

    private val _uiState = MutableStateFlow(CartUiState())
    val uiState: StateFlow<CartUiState> = _uiState.asStateFlow()

    private val users = mutableMapOf("user123" to "password")
    private val userNames = mutableMapOf("user123" to "홍길동")
    private var rfidCounter = 0

    fun navigateTo(screen: Screen) {
        _uiState.value = _uiState.value.copy(currentScreen = screen)
    }

    fun login(id: String, pw: String): Boolean {
        if (users[id] == pw) {
            _uiState.value = _uiState.value.copy(
                currentScreen = Screen.DASHBOARD,
                userName = userNames[id] ?: id
            )
            return true
        }
        return false
    }

    fun signUp(name: String, phone: String, id: String, pw: String): Boolean {
        users[id] = pw
        userNames[id] = name
        _uiState.value = _uiState.value.copy(
            currentScreen = Screen.DASHBOARD,
            userName = name
        )
        return true
    }

    fun logout() {
        _uiState.value = CartUiState()
        navigateTo(Screen.LOGIN)
    }

    fun matchCart(cartId: String) {
        _uiState.value = _uiState.value.copy(
            matchedCartId = cartId,
            currentScreen = Screen.SHOPPING,
            cartBattery = 85,
            trackingState = TrackingState.FOLLOWING,
        )
        showVoice("카트와 연결됐어요. 안전하게 따라갈게요.")
    }

    fun setTrackingState(state: TrackingState) {
        _uiState.value = _uiState.value.copy(trackingState = state)
        val msg = when (state) {
            TrackingState.FOLLOWING -> "자동 추종을 시작해요."
            TrackingState.PAUSED -> "카트가 멈췄어요."
            else -> ""
        }
        if (msg.isNotEmpty()) showVoice(msg)
    }

    fun simulateRfidScan(name: String, price: Int, emoji: String) {
        val existing = _uiState.value.shoppingList.find { it.name == name }
        val newList = if (existing != null) {
            _uiState.value.shoppingList.map {
                if (it.name == name) it.copy(quantity = it.quantity + 1) else it
            }
        } else {
            rfidCounter++
            _uiState.value.shoppingList + CartItem(
                id = "RF%04d".format(rfidCounter),
                name = name,
                price = price,
                quantity = 1,
                imageEmoji = emoji,
            )
        }
        _uiState.value = _uiState.value.copy(shoppingList = newList)
        showVoice("$name 이(가) 카트에 담겼어요.")
    }

    fun removeItem(item: CartItem) {
        _uiState.value = _uiState.value.copy(
            shoppingList = _uiState.value.shoppingList.filter { it.id != item.id }
        )
    }

    fun formatPrice(price: Int): String = "%,d원".format(price)

    // 사용하지 않지만 기존 ViewModel과의 호환을 위해 유지
    fun publishManualControl(direction: String) = Unit
    fun toggleSimulationPanel() = Unit

    private fun showVoice(message: String) {
        _uiState.value = _uiState.value.copy(latestVoiceGuidance = message)
        viewModelScope.launch {
            delay(3500)
            if (_uiState.value.latestVoiceGuidance == message) {
                _uiState.value = _uiState.value.copy(latestVoiceGuidance = "")
            }
        }
    }
}
