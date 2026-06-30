package com.example.ui.screens

import android.graphics.Bitmap
import androidx.compose.ui.graphics.asImageBitmap
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import java.text.NumberFormat
import java.util.Locale
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate as rotateDraw
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.viewmodel.*
import kotlinx.coroutines.delay
import androidx.compose.ui.graphics.ImageBitmap

/* ============================================================
 *  CartMe · 디자인 토큰  (CartMe.dc.html 기반)
 * ============================================================ */
private val Blue        = Color(0xFF1F7BFF)   // primary
private val BlueSoft    = Color(0xFFE9F2FF)   // chip / soft accent
private val Navy        = Color(0xFF16224A)   // 본문 진한 텍스트
private val NavyDeep    = Color(0xFF0E1B33)   // 페어링 배경
private val ScreenBg    = Color(0xFFF5F8FC)   // 일반 화면 배경
private val Surface     = Color(0xFFFFFFFF)
private val InputBg     = Color(0xFFF5F8FC)
private val InputBorder = Color(0xFFEAEEF5)
private val TextSub     = Color(0xFF8A93A6)
private val TextFaint   = Color(0xFF9AA3B4)
private val Green       = Color(0xFF22C55E)
private val OnDarkSub   = Color(0xFF9FB2D6)
private val LightBlue   = Color(0xFFD7E8FF)
private val Danger      = Color(0xFFE5484D)
private val Line        = Color(0xFFEEF1F6)
private val Cheek       = Color(0xFFFFC2D1)
private val MascotRing  = Color(0xFFBCD7FF)
private val MascotMesh  = Color(0xFFDCEBFF)

private val RBtn   = 18.dp
private val RInput = 16.dp
private val RCard  = 20.dp

private fun won(n: Int): String = NumberFormat.getNumberInstance(Locale.KOREA).format(n)

/* ============================================================
 *  ENTRY
 * ============================================================ */
@Composable
fun CartAppContent(viewModel: CartViewModel, innerPadding: PaddingValues) {
    val uiState by viewModel.uiState.collectAsState()

    // 상태바 영역까지 화면별 배경색이 채워지도록 바깥 Box 배경을 화면에 맞춘다.
    val screenBg = when (uiState.currentScreen) {
        Screen.SPLASH, Screen.SIGNUP, Screen.COMPLETION -> Blue
        Screen.LOGIN -> Surface
        Screen.DASHBOARD -> NavyDeep
        Screen.SHOPPING, Screen.PAYMENT -> ScreenBg
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(screenBg)
            .padding(innerPadding)
    ) {
        Crossfade(targetState = uiState.currentScreen, label = "screen") { screen ->
            when (screen) {
                Screen.SPLASH -> SplashScreen { viewModel.navigateTo(Screen.LOGIN) }
                Screen.LOGIN -> LoginScreen(
                    errorMessage = uiState.errorMessage,
                    isLoading = uiState.isLoading,
                    onLogin = { email, pw -> viewModel.login(email, pw) },
                    onSignUp = { viewModel.navigateTo(Screen.SIGNUP) }
                )
                Screen.SIGNUP -> SignUpScreen(
                    errorMessage = uiState.errorMessage,
                    isLoading = uiState.isLoading,
                    onSubmit = { n, p, email, pw -> viewModel.signUp(n, p, email, pw) },
                    onBack = { viewModel.navigateTo(Screen.LOGIN) }
                )
                Screen.DASHBOARD -> {
                    LaunchedEffect(Unit) { viewModel.generateQR() }
                    PairScreen(
                        uiState = uiState,
                        onGenerateQR = { viewModel.generateQR() },
                        onLogout = { viewModel.logout() }
                    )
                }
                Screen.SHOPPING -> ShoppingScreen(
                    uiState = uiState,
                    viewModel = viewModel,
                    onCheckout = { viewModel.navigateTo(Screen.PAYMENT) }
                )
                Screen.PAYMENT -> PaymentScreen(
                    uiState = uiState,
                    isLoading = uiState.isLoading,
                    errorMessage = uiState.errorMessage,
                    onPay = { viewModel.completeOrder() },
                    onBack = { viewModel.navigateTo(Screen.SHOPPING) }
                )
                Screen.COMPLETION -> CompletionScreen(
                    uiState = uiState,
                    onRestart = { viewModel.logout() }
                )
            }
        }

        if (uiState.currentScreen == Screen.DASHBOARD || uiState.currentScreen == Screen.SHOPPING) {
            VoiceToast(
                message = uiState.latestVoiceGuidance,
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
            )
        }
    }
}

/* ============================================================
 *  Mascot — 장바구니 캐릭터 (Canvas, CartMe.dc.html Mascot 재현)
 *  mood: "wave" | "idle" | "celebrate"
 * ============================================================ */
@Composable
private fun Mascot(
    width: Dp,
    mood: String = "wave",
    ring: Color = MascotRing,
    mesh: Color = MascotMesh,
) {
    // 둥실 떠오르는 idle 모션
    val floatT = rememberInfiniteTransition(label = "mascotFloat")
    val dy by floatT.animateFloat(
        initialValue = 0f, targetValue = -7f,
        animationSpec = infiniteRepeatable(tween(1400, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "dy"
    )
    // 손 흔들기
    val waveDeg by floatT.animateFloat(
        initialValue = 8f, targetValue = -22f,
        animationSpec = infiniteRepeatable(tween(700, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "wave"
    )
    val armExtra = when (mood) {
        "wave" -> waveDeg
        "celebrate" -> -46f
        else -> 0f
    }

    val height = width * (235f / 200f)
    Canvas(modifier = Modifier.size(width, height).offset(y = dy.dp)) {
        val sx = size.width / 200f
        val sy = size.height / 235f
        fun px(x: Float) = x * sx
        fun py(y: Float) = y * sy

        // handle (ring 곡선)
        val handle = Path().apply {
            moveTo(px(34f), py(70f))
            cubicTo(px(34f), py(44f), px(56f), py(42f), px(70f), py(42f))
        }
        drawPath(handle, ring, style = Stroke(width = 11f * sx, cap = StrokeCap.Round))

        // 왼팔
        rotateDraw(18f, pivot = Offset(px(44f), py(130f))) {
            drawRoundRect(Color.White, topLeft = Offset(px(34f), py(118f)),
                size = Size(20f * sx, 46f * sy), cornerRadius = CornerRadius(10f * sx, 10f * sy))
        }
        // 오른팔 (인사)
        rotateDraw(-18f + armExtra, pivot = Offset(px(156f), py(130f))) {
            drawRoundRect(Color.White, topLeft = Offset(px(146f), py(116f)),
                size = Size(20f * sx, 46f * sy), cornerRadius = CornerRadius(10f * sx, 10f * sy))
        }
        // 바구니 몸통
        drawRoundRect(Color.White, topLeft = Offset(px(46f), py(78f)),
            size = Size(108f * sx, 104f * sy), cornerRadius = CornerRadius(30f * sx, 30f * sy))
        // mesh
        drawLine(mesh, Offset(px(78f), py(92f)), Offset(px(78f), py(168f)), strokeWidth = 4f * sx, cap = StrokeCap.Round)
        drawLine(mesh, Offset(px(122f), py(92f)), Offset(px(122f), py(168f)), strokeWidth = 4f * sx, cap = StrokeCap.Round)
        drawLine(mesh, Offset(px(58f), py(150f)), Offset(px(142f), py(150f)), strokeWidth = 4f * sx, cap = StrokeCap.Round)
        // 볼
        drawOval(Cheek, topLeft = Offset(px(70f - 9f), py(132f - 6f)), size = Size(18f * sx, 12f * sy))
        drawOval(Cheek, topLeft = Offset(px(130f - 9f), py(132f - 6f)), size = Size(18f * sx, 12f * sy))
        // 눈
        drawOval(Navy, topLeft = Offset(px(83f - 6f), py(118f - 8.5f)), size = Size(12f * sx, 17f * sy))
        drawOval(Navy, topLeft = Offset(px(117f - 6f), py(118f - 8.5f)), size = Size(12f * sx, 17f * sy))
        drawCircle(Color.White, radius = 2f * sx, center = Offset(px(85f), py(115f)))
        drawCircle(Color.White, radius = 2f * sx, center = Offset(px(119f), py(115f)))
        // 미소
        val smile = Path().apply {
            moveTo(px(90f), py(134f))
            quadraticBezierTo(px(100f), py(144f), px(110f), py(134f))
        }
        drawPath(smile, Navy, style = Stroke(width = 4f * sx, cap = StrokeCap.Round))
        // 다리
        drawRoundRect(Color.White, topLeft = Offset(px(74f), py(180f)),
            size = Size(12f * sx, 20f * sy), cornerRadius = CornerRadius(6f * sx, 6f * sy))
        drawRoundRect(Color.White, topLeft = Offset(px(114f), py(180f)),
            size = Size(12f * sx, 20f * sy), cornerRadius = CornerRadius(6f * sx, 6f * sy))
        // 바퀴
        drawCircle(ring, radius = 14f * sx, center = Offset(px(80f), py(208f)))
        drawCircle(ring, radius = 14f * sx, center = Offset(px(120f), py(208f)))
        drawCircle(Color.White, radius = 5f * sx, center = Offset(px(80f), py(208f)))
        drawCircle(Color.White, radius = 5f * sx, center = Offset(px(120f), py(208f)))
    }
}

/* ============================================================
 *  QR 코드 이미지 (ZXing core → Bitmap → Compose Image)
 * ============================================================ */
@Composable
private fun QrCodeImage(content: String, size: Dp = 180.dp) {
    val density = LocalDensity.current
    val sizePx  = with(density) { size.roundToPx() }

    val bitmap: ImageBitmap? = remember(content) {
        if (content.isBlank()) return@remember null
        try {
            val writer    = QRCodeWriter()
            val bitMatrix = writer.encode(content, BarcodeFormat.QR_CODE, sizePx, sizePx)
            val bmp = Bitmap.createBitmap(sizePx, sizePx, Bitmap.Config.RGB_565)
            for (x in 0 until sizePx) {
                for (y in 0 until sizePx) {
                    bmp.setPixel(x, y, if (bitMatrix[x, y]) android.graphics.Color.parseColor("#16224A")
                                        else android.graphics.Color.WHITE)
                }
            }
            bmp.asImageBitmap()
        } catch (e: Exception) { null }
    }

    if (bitmap != null) {
        androidx.compose.foundation.Image(
            bitmap = bitmap,
            contentDescription = "QR Code",
            modifier = Modifier.size(size)
        )
    } else {
        Box(
            modifier = Modifier.size(size).border(2.dp, InputBorder, RoundedCornerShape(RInput)),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Filled.QrCode, contentDescription = null, tint = TextFaint, modifier = Modifier.size(48.dp))
                Spacer(Modifier.height(8.dp))
                Text("버튼을 눌러 QR 생성", fontSize = 12.sp, color = TextFaint)
            }
        }
    }
}

/* ============================================================
 *  공용 컴포넌트
 * ============================================================ */
private enum class BtnVariant { Filled, Outline, Light }

@Composable
private fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
    variant: BtnVariant = BtnVariant.Filled,
    height: Dp = 58.dp,
) {
    val container: Color; val content: Color
    when (variant) {
        BtnVariant.Filled  -> { container = Blue;    content = Color.White }
        BtnVariant.Outline -> { container = InputBg; content = Navy }
        BtnVariant.Light   -> { container = Color.White; content = Blue }
    }
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(height),
        shape = RoundedCornerShape(RBtn),
        elevation = if (variant == BtnVariant.Filled)
            ButtonDefaults.buttonElevation(defaultElevation = 8.dp, pressedElevation = 2.dp) else null,
        border = if (variant == BtnVariant.Outline)
            androidx.compose.foundation.BorderStroke(2.dp, InputBorder) else null,
        colors = ButtonDefaults.buttonColors(
            containerColor = container,
            contentColor = content,
            disabledContainerColor = Color(0xFFBFD3F2),
            disabledContentColor = Color.White
        )
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
    }
}

@Composable
private fun AppInput(
    value: String,
    onValueChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier.fillMaxWidth().height(58.dp),
        singleLine = true,
        shape = RoundedCornerShape(RInput),
        placeholder = { Text(placeholder, color = TextFaint, fontSize = 15.sp) },
        textStyle = androidx.compose.ui.text.TextStyle(
            fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Navy
        ),
        visualTransformation = if (password) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Blue,
            unfocusedBorderColor = InputBorder,
            focusedContainerColor = InputBg,
            unfocusedContainerColor = InputBg,
            cursorColor = Blue,
        )
    )
}

@Composable
private fun PulsingDot(color: Color, size: Int = 9) {
    val t = rememberInfiniteTransition(label = "dot")
    val a by t.animateFloat(
        initialValue = 1f, targetValue = 2.6f,
        animationSpec = infiniteRepeatable(tween(1600, easing = LinearEasing), RepeatMode.Restart),
        label = "scale"
    )
    Box(contentAlignment = Alignment.Center, modifier = Modifier.size((size + 8).dp)) {
        Canvas(Modifier.size(size.dp)) {
            drawCircle(color = color.copy(alpha = (1.6f - a / 2.6f).coerceIn(0f, 1f) * 0.6f),
                radius = this.size.minDimension / 2 * a)
            drawCircle(color = color, radius = this.size.minDimension / 2)
        }
    }
}

@Composable
private fun VoiceToast(message: String, modifier: Modifier = Modifier) {
    AnimatedVisibility(
        visible = message.isNotBlank(),
        enter = fadeIn() + slideInVertically { it / 2 },
        exit = fadeOut(),
        modifier = modifier
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RInput)).background(Navy).padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(modifier = Modifier.size(30.dp).clip(RoundedCornerShape(9.dp)).background(Blue),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.VolumeUp, contentDescription = null, tint = Color.White, modifier = Modifier.size(17.dp))
            }
            Spacer(Modifier.width(11.dp))
            Text(message, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium, lineHeight = 18.sp)
        }
    }
}

@Composable
private fun LogoutChip(onClick: () -> Unit, onDark: Boolean = false) {
    Box(
        modifier = Modifier.size(40.dp).clip(RoundedCornerShape(12.dp))
            .background(if (onDark) Color.White.copy(alpha = 0.14f) else Surface)
            .then(if (onDark) Modifier else Modifier.border(1.dp, InputBorder, RoundedCornerShape(12.dp)))
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) {
        Icon(Icons.Filled.ExitToApp, contentDescription = "로그아웃",
            tint = if (onDark) Color.White else TextSub, modifier = Modifier.size(19.dp))
    }
}

/* ============================================================
 *  SPLASH
 * ============================================================ */
@Composable
private fun SplashScreen(onDone: () -> Unit) {
    LaunchedEffect(Unit) { delay(2500); onDone() }
    Box(
        Modifier.fillMaxSize().background(Blue).clickable { onDone() },
        contentAlignment = Alignment.Center
    ) {
        // 장식 원
        Box(Modifier.align(Alignment.TopStart).offset(x = (-70).dp, y = (-80).dp)
            .size(260.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.10f)))
        Box(Modifier.align(Alignment.BottomEnd).offset(x = 50.dp, y = 60.dp)
            .size(220.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.08f)))

        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text("CartMe", fontSize = 56.sp, fontWeight = FontWeight.Black, color = Color.White,
                letterSpacing = (-1).sp)
            Spacer(Modifier.height(8.dp))
            Text("스마트 카트로 더 가벼운 장보기", fontSize = 16.sp, fontWeight = FontWeight.SemiBold,
                color = LightBlue)
            Spacer(Modifier.height(18.dp))
            Mascot(width = 200.dp, mood = "wave")
        }
        Text("탭하여 시작하기", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            color = Color.White.copy(alpha = 0.85f),
            modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 54.dp))
    }
}

/* ============================================================
 *  LOGIN
 * ============================================================ */
@Composable
private fun LoginScreen(
    errorMessage: String,
    isLoading: Boolean,
    onLogin: (String, String) -> Unit,
    onSignUp: () -> Unit,
) {
    var email by remember { mutableStateOf("") }
    var pw    by remember { mutableStateOf("") }
    val focus = LocalFocusManager.current

    Box(Modifier.fillMaxSize().background(Surface)) {
        Box(Modifier.align(Alignment.TopEnd).padding(top = 20.dp, end = 18.dp).width(118.dp)) {
            Mascot(width = 118.dp, mood = "idle", ring = Color(0xFFBFD8FF))
        }
        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 30.dp, end = 30.dp, top = 96.dp, bottom = 36.dp)
        ) {
            Text("다시 만나서\n반가워요", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Navy,
                lineHeight = 40.sp, letterSpacing = (-0.5).sp)
            Spacer(Modifier.height(10.dp))
            Text("로그인하고 똑똑한 장보기를 시작해요", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = TextSub)

            Spacer(Modifier.height(40.dp))
            AppInput(email, { email = it }, "이메일", keyboardType = KeyboardType.Email)
            Spacer(Modifier.height(14.dp))
            AppInput(pw, { pw = it }, "비밀번호", password = true)

            if (errorMessage.isNotBlank()) {
                Spacer(Modifier.height(10.dp))
                Text(errorMessage, color = Danger, fontSize = 12.5.sp)
            }

            Spacer(Modifier.height(8.dp))
            Text("비밀번호를 잊으셨나요?", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextSub,
                modifier = Modifier.align(Alignment.End))

            Spacer(Modifier.height(36.dp))
            PrimaryButton(
                text = if (isLoading) "로그인 중..." else "로그인",
                enabled = !isLoading,
                onClick = { focus.clearFocus(); onLogin(email, pw) }
            )
            Spacer(Modifier.height(6.dp))
            Box(Modifier.fillMaxWidth().height(48.dp).clickable { onSignUp() }, contentAlignment = Alignment.Center) {
                Text("이메일로 회원가입", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Blue)
            }
        }
    }
}

/* ============================================================
 *  SIGN-UP — 멀티스텝 위저드 (이름·휴대폰·이메일·비밀번호)
 * ============================================================ */
private data class SignupStep(
    val label: String, val placeholder: String, val type: KeyboardType,
    val password: Boolean, val title: String, val subtitle: String, val mood: String,
)

@Composable
private fun SignUpScreen(
    errorMessage: String,
    isLoading: Boolean,
    onSubmit: (String, String, String, String) -> Unit,
    onBack: () -> Unit,
) {
    val steps = remember {
        listOf(
            SignupStep("이름", "예) 김카트", KeyboardType.Text, false,
                "이름을\n알려주세요", "어떻게 불러드리면 될까요?", "wave"),
            SignupStep("휴대폰 번호", "010-0000-0000", KeyboardType.Phone, false,
                "연락처를\n입력해주세요", "주문 알림을 받을 번호예요 (선택)", "idle"),
            SignupStep("이메일", "you@example.com", KeyboardType.Email, false,
                "이메일을\n입력해주세요", "로그인할 때 사용할 이메일이에요", "idle"),
            SignupStep("비밀번호", "6자 이상 입력해주세요", KeyboardType.Password, true,
                "비밀번호를\n만들어주세요", "안전하게 설정해요", "celebrate"),
        )
    }
    var step  by remember { mutableStateOf(0) }
    var name  by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var pw    by remember { mutableStateOf("") }
    val focus = LocalFocusManager.current

    val values = listOf(name, phone, email, pw)
    val cur = steps[step]
    val canNext = when (step) {
        0 -> name.trim().isNotEmpty()
        1 -> true                                   // 휴대폰은 선택
        2 -> Regex(".+@.+\\..+").matches(email)
        else -> pw.length >= 6
    }
    val last = step == steps.lastIndex

    Box(Modifier.fillMaxSize().background(Blue)) {
        // 장식 원
        Box(Modifier.align(Alignment.TopEnd).offset(x = 70.dp, y = (-90).dp)
            .size(240.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.09f)))

        // 상단 바: 뒤로 + 단계 점
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, top = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier.size(40.dp).clip(CircleShape).background(Color.White.copy(alpha = 0.18f))
                    .clickable { if (step > 0) step-- else onBack() },
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Color.White, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.width(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
                steps.indices.forEach { i ->
                    val w by animateDpAsState(if (i == step) 24.dp else 8.dp, label = "dotw")
                    Box(Modifier.height(8.dp).width(w).clip(RoundedCornerShape(99.dp))
                        .background(if (i <= step) Color.White else Color.White.copy(alpha = 0.38f)))
                }
            }
        }

        // 패널 (타이틀 + 마스코트)
        Column(
            modifier = Modifier.fillMaxWidth().padding(top = 96.dp).padding(horizontal = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            AnimatedContent(targetState = step, label = "panel",
                transitionSpec = {
                    (slideInHorizontally { it / 3 } + fadeIn()) togetherWith
                        (slideOutHorizontally { -it / 3 } + fadeOut())
                }) { s ->
                val st = steps[s]
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(st.title, fontSize = 29.sp, fontWeight = FontWeight.Black, color = Color.White,
                        lineHeight = 38.sp, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(10.dp))
                    Text(st.subtitle, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = LightBlue,
                        modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(18.dp))
                    Mascot(width = 190.dp, mood = st.mood)
                }
            }
        }

        // 하단 시트 (입력 + 다음)
        Column(
            modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .clip(RoundedCornerShape(topStart = 32.dp, topEnd = 32.dp)).background(Surface)
                .padding(start = 30.dp, end = 30.dp, top = 28.dp, bottom = 38.dp)
        ) {
            Text(cur.label, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub)
            Spacer(Modifier.height(10.dp))
            AppInput(
                value = values[step],
                onValueChange = { v -> when (step) { 0 -> name = v; 1 -> phone = v; 2 -> email = v; else -> pw = v } },
                placeholder = cur.placeholder,
                password = cur.password,
                keyboardType = cur.type,
            )
            if (errorMessage.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(errorMessage, color = Danger, fontSize = 12.sp)
            }
            Spacer(Modifier.height(16.dp))
            PrimaryButton(
                text = if (last) (if (isLoading) "가입 중..." else "가입 완료") else "다음",
                enabled = canNext && !isLoading,
                onClick = {
                    if (last) { focus.clearFocus(); onSubmit(name, phone, email, pw) }
                    else step++
                }
            )
        }
    }
}

/* ============================================================
 *  PAIR (대시보드 / QR 매칭) — 다크 네이비, 실제 QR + 타이머 + 재발급
 * ============================================================ */
@Composable
private fun PairScreen(
    uiState: CartUiState,
    onGenerateQR: () -> Unit,
    onLogout: () -> Unit,
) {
    Box(Modifier.fillMaxSize().background(NavyDeep)) {
        Box(Modifier.align(Alignment.TopStart).offset(x = (-60).dp, y = (-70).dp)
            .size(200.dp).clip(CircleShape).background(Color(0x1F7FB4FF)))

        Column(
            modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState())
                .padding(start = 30.dp, end = 30.dp, top = 20.dp, bottom = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                LogoutChip(onLogout, onDark = true)
            }
            Spacer(Modifier.height(8.dp))
            Text("카트로 연결하기", fontSize = 28.sp, fontWeight = FontWeight.Black, color = Color.White,
                textAlign = TextAlign.Center)
            Spacer(Modifier.height(10.dp))
            Text(
                if (uiState.qrToken.isBlank()) "아래 버튼을 눌러 QR 코드를 만들어\n카트 카메라에 비춰주세요"
                else "매장 카트 손잡이의 카메라에\nQR을 비추면 바로 연결돼요",
                fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = OnDarkSub,
                textAlign = TextAlign.Center, lineHeight = 21.sp
            )

            Spacer(Modifier.height(28.dp))
            // 흰색 QR 카드 (실제 QR)
            Box(Modifier.clip(RoundedCornerShape(28.dp)).background(Surface).padding(22.dp)) {
                QrCodeImage(content = uiState.qrToken, size = 180.dp)
            }

            if (uiState.qrToken.isNotBlank()) {
                Spacer(Modifier.height(16.dp))
                var timeLeft by remember(uiState.qrToken) { mutableStateOf(180) }
                LaunchedEffect(uiState.qrToken) {
                    timeLeft = 180
                    while (timeLeft > 0) { delay(1000L); timeLeft-- }
                }
                val timeString = "%02d:%02d".format(timeLeft / 60, timeLeft % 60)
                val expired = timeLeft == 0
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Timer, contentDescription = null,
                        tint = if (expired) Danger else LightBlue, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(if (expired) "시간 만료 · 재발급이 필요해요" else "남은 시간 $timeString",
                        fontSize = 14.sp, fontWeight = FontWeight.Bold,
                        color = if (expired) Danger else Color.White)
                }
                Spacer(Modifier.height(6.dp))
                Text("3분 내에 스캔해 주세요 · 스캔 시 자동 이동",
                    fontSize = 11.5.sp, color = OnDarkSub, textAlign = TextAlign.Center)
            }

            Spacer(Modifier.height(18.dp))
            Mascot(width = 128.dp, mood = "idle", ring = Color(0xFF3A5C99), mesh = Color(0xFF21345C))

            Spacer(Modifier.height(24.dp))
            PrimaryButton(
                text = if (uiState.isLoading) "재발급 중..." else "QR 코드 재발급",
                enabled = !uiState.isLoading,
                onClick = onGenerateQR,
                leadingIcon = Icons.Filled.Refresh
            )
        }
    }
}

/* ============================================================
 *  SHOPPING — 장바구니는 socket:cart:updated 로 자동 갱신
 * ============================================================ */
@Composable
private fun ShoppingScreen(uiState: CartUiState, viewModel: CartViewModel, onCheckout: () -> Unit) {
    val count = uiState.shoppingList.sumOf { it.quantity }
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(Modifier.fillMaxSize()) {
            // 헤더
            Row(modifier = Modifier.fillMaxWidth().padding(start = 22.dp, end = 18.dp, top = 14.dp, bottom = 4.dp),
                horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("나의 카트", fontSize = 26.sp, fontWeight = FontWeight.Black, color = Navy)
                    Spacer(Modifier.width(10.dp))
                    Text("${count}개 담김", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = Blue,
                        modifier = Modifier.clip(RoundedCornerShape(99.dp)).background(BlueSoft)
                            .padding(horizontal = 12.dp, vertical = 6.dp))
                }
                LogoutChip({ viewModel.logout() })
            }

            Column(modifier = Modifier.weight(1f).verticalScroll(rememberScrollState())
                .padding(horizontal = 22.dp)) {
                Spacer(Modifier.height(12.dp))
                CartControlCard(uiState,
                    onSet = { viewModel.setTrackingState(it) },
                    onReturn = { viewModel.completeOrder() })

                Spacer(Modifier.height(18.dp))
                Text("담은 상품 $count", fontSize = 14.sp, fontWeight = FontWeight.ExtraBold, color = Navy,
                    modifier = Modifier.padding(start = 4.dp))
                Spacer(Modifier.height(12.dp))

                if (uiState.shoppingList.isEmpty()) {
                    EmptyCart()
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        uiState.shoppingList.forEach { item ->
                            ItemRow(item) { viewModel.removeItem(item) }
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))
            }

            // 하단 결제 시트
            Column(
                modifier = Modifier.fillMaxWidth()
                    .clip(RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)).background(Surface)
                    .padding(horizontal = 24.dp, vertical = 20.dp)
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically) {
                    Text("총 결제금액", fontSize = 15.sp, fontWeight = FontWeight.Medium, color = TextSub)
                    Text("${won(total)}원", fontSize = 24.sp, fontWeight = FontWeight.Black, color = Navy)
                }
                Spacer(Modifier.height(16.dp))
                PrimaryButton("결제하기", onCheckout, enabled = uiState.shoppingList.isNotEmpty())
            }
        }
    }
}

@Composable
private fun CartControlCard(uiState: CartUiState, onSet: (TrackingState) -> Unit, onReturn: () -> Unit) {
    val following = uiState.trackingState == TrackingState.FOLLOWING
    val tone: Color; val toneBg: Color; val icon: ImageVector; val label: String; val desc: String
    when (uiState.trackingState) {
        TrackingState.FOLLOWING -> { tone = Blue; toneBg = BlueSoft
            icon = Icons.Filled.NearMe; label = "자동 주행 중"; desc = "내 위치를 따라 이동하고 있어요" }
        TrackingState.PAUSED -> { tone = TextSub; toneBg = InputBg
            icon = Icons.Filled.Pause; label = "일시 정지"; desc = "추종 시작을 누르면 다시 따라가요" }
        TrackingState.LOST_TRACKING -> { tone = Color(0xFFE0A100); toneBg = Color(0x1FE0A100)
            icon = Icons.Filled.Shield; label = "사용자 인식 실패"; desc = "카트 정면 카메라 앞에 서주세요" }
        TrackingState.DISCONNECTED -> { tone = Danger; toneBg = Color(0x1AE5484D)
            icon = Icons.Filled.Shield; label = "통신 지연"; desc = "Wi-Fi 연결 상태를 확인해 주세요" }
    }

    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface).padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PulsingDot(Green)
                Spacer(Modifier.width(4.dp))
                Text("${uiState.matchedCartId.ifBlank { "CART-01" }} 연결됨",
                    fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.BatteryFull, contentDescription = null,
                    tint = if (uiState.cartBattery > 20) Green else Danger, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(4.dp))
                Text("${uiState.cartBattery}%", fontSize = 13.sp, fontWeight = FontWeight.Bold,
                    color = if (uiState.cartBattery > 20) Green else Danger)
            }
        }
        Spacer(Modifier.height(13.dp))
        Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(15.dp)).background(toneBg)
            .padding(horizontal = 14.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(38.dp).clip(RoundedCornerShape(12.dp)).background(tone),
                contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(20.dp))
            }
            Spacer(Modifier.width(11.dp))
            Column {
                Text(label, fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = tone)
                Text(desc, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = TextSub)
            }
        }
        Spacer(Modifier.height(11.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (following) {
                PrimaryButton("정지", { onSet(TrackingState.PAUSED) }, modifier = Modifier.weight(1f),
                    leadingIcon = Icons.Filled.Pause, variant = BtnVariant.Outline, height = 46.dp)
            } else {
                PrimaryButton("추종 시작", { onSet(TrackingState.FOLLOWING) }, modifier = Modifier.weight(1f),
                    leadingIcon = Icons.Filled.PlayArrow, height = 46.dp)
            }
            PrimaryButton("복귀", onReturn, modifier = Modifier.weight(1f),
                leadingIcon = Icons.Filled.Home, variant = BtnVariant.Outline, height = 46.dp)
        }
    }
}

@Composable
private fun ItemRow(item: CartItem, onRemove: () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface)
        .padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(56.dp).clip(RoundedCornerShape(15.dp)).background(BlueSoft),
            contentAlignment = Alignment.Center) {
            Text(item.imageEmoji, fontSize = 26.sp)
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(item.name, fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Navy,
                maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${item.id} · 수량 ${item.quantity}", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                color = TextFaint, modifier = Modifier.padding(top = 3.dp))
        }
        Spacer(Modifier.width(8.dp))
        Text("${won(item.price * item.quantity)}원", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
        Box(Modifier.size(34.dp).clip(RoundedCornerShape(9.dp)).clickable { onRemove() },
            contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.DeleteOutline, contentDescription = "삭제", tint = TextFaint, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun EmptyCart() {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Icon(Icons.Filled.ShoppingCart, contentDescription = null, tint = TextFaint, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(10.dp))
        Text("카트가 비어있어요", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = TextSub)
        Text("로봇 RFID가 상품을 자동 인식해요", fontSize = 12.5.sp, color = TextFaint)
    }
}

/* ============================================================
 *  PAYMENT
 * ============================================================ */
@Composable
private fun PaymentScreen(
    uiState: CartUiState,
    isLoading: Boolean,
    errorMessage: String,
    onPay: () -> Unit,
    onBack: () -> Unit,
) {
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    Box(Modifier.fillMaxSize().background(ScreenBg)) {
        Column(Modifier.fillMaxSize()) {
            Row(modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 20.dp, top = 14.dp, bottom = 8.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).clickable { onBack() },
                    contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Navy, modifier = Modifier.size(22.dp))
                }
                Spacer(Modifier.width(4.dp))
                Text("결제하기", fontSize = 26.sp, fontWeight = FontWeight.Black, color = Navy)
            }

            Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 24.dp)) {
                Spacer(Modifier.height(10.dp))
                Text("결제수단", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub,
                    modifier = Modifier.padding(start = 2.dp))
                Spacer(Modifier.height(10.dp))
                Row(modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface)
                    .border(2.dp, Blue, RoundedCornerShape(RCard)).padding(18.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(46.dp).clip(RoundedCornerShape(13.dp)).background(Blue),
                        contentAlignment = Alignment.Center) {
                        Text("C", fontSize = 18.sp, fontWeight = FontWeight.Black, color = Color.White)
                    }
                    Spacer(Modifier.width(14.dp))
                    Column(Modifier.weight(1f)) {
                        Text("CartPay 간편결제", fontSize = 16.sp, fontWeight = FontWeight.Bold, color = Navy)
                        Text("신한카드 ····3204", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = TextFaint,
                            modifier = Modifier.padding(top = 2.dp))
                    }
                    Box(Modifier.size(22.dp).clip(CircleShape).background(Blue), contentAlignment = Alignment.Center) {
                        Icon(Icons.Filled.Check, contentDescription = null, tint = Color.White, modifier = Modifier.size(14.dp))
                    }
                }

                Spacer(Modifier.height(24.dp))
                Text("결제 금액", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextSub,
                    modifier = Modifier.padding(start = 2.dp))
                Spacer(Modifier.height(10.dp))
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(RCard)).background(Surface).padding(18.dp)) {
                    AmountRow("상품 금액", "${won(total)}원")
                    Spacer(Modifier.height(13.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("배송비", fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF5B6479))
                        Text("무료", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Blue)
                    }
                    Spacer(Modifier.height(14.dp))
                    Box(Modifier.fillMaxWidth().height(1.dp).background(Line))
                    Spacer(Modifier.height(14.dp))
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically) {
                        Text("총 결제금액", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Navy)
                        Text("${won(total)}원", fontSize = 22.sp, fontWeight = FontWeight.Black, color = Blue)
                    }
                }

                if (errorMessage.isNotBlank()) {
                    Spacer(Modifier.height(10.dp))
                    Text(errorMessage, color = Danger, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 2.dp))
                }
            }

            Column(Modifier.padding(horizontal = 24.dp).padding(bottom = 34.dp, top = 8.dp)) {
                PrimaryButton(
                    text = if (isLoading) "결제 처리 중..." else "${won(total)}원 결제하기",
                    enabled = !isLoading,
                    onClick = onPay
                )
            }
        }
    }
}

@Composable
private fun AmountRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF5B6479))
        Text(value, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF5B6479))
    }
}

/* ============================================================
 *  COMPLETION — 컨페티 + 마스코트
 * ============================================================ */
@Composable
private fun CompletionScreen(uiState: CartUiState, onRestart: () -> Unit) {
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    var popped by remember { mutableStateOf(false) }
    val pop by animateFloatAsState(if (popped) 1f else 0.8f,
        spring(dampingRatio = 0.45f, stiffness = Spring.StiffnessLow), label = "pop")
    LaunchedEffect(Unit) { popped = true }

    BoxWithConstraints(Modifier.fillMaxSize().background(Blue)) {
        Confetti(maxWidth, maxHeight)

        Column(
            modifier = Modifier.fillMaxSize().padding(horizontal = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Box(Modifier.size(96.dp).scale(pop).clip(CircleShape).background(Color.White),
                contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Check, contentDescription = null, tint = Blue, modifier = Modifier.size(54.dp))
            }
            Spacer(Modifier.height(26.dp))
            Text("결제 완료!", fontSize = 30.sp, fontWeight = FontWeight.Black, color = Color.White)
            Spacer(Modifier.height(8.dp))
            Text("${won(total)}원 결제되었어요", fontSize = 16.sp, fontWeight = FontWeight.SemiBold, color = LightBlue)
            Spacer(Modifier.height(14.dp))
            Mascot(width = 170.dp, mood = "celebrate")
            Spacer(Modifier.height(4.dp))
            Text("카트는 매장 반납대로 복귀하고 있어요", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                color = Color(0xFFBCD7FF))
            Spacer(Modifier.height(36.dp))
            PrimaryButton("처음으로", onRestart, variant = BtnVariant.Light)
        }
    }
}

@Composable
private fun Confetti(areaW: Dp, areaH: Dp) {
    val colors = listOf(Color(0xFFFFD64D), Color.White, Color(0xFF7FB4FF), Color(0xFFFF9DBB))
    val t = rememberInfiniteTransition(label = "confetti")
    val prog by t.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(2600, easing = LinearEasing), RepeatMode.Restart),
        label = "fall"
    )
    Box(Modifier.fillMaxSize()) {
        repeat(14) { i ->
            val phase = (prog + i / 14f) % 1f
            val x = (6f + (i * 6.4f) % 88f) / 100f * areaW.value
            val y = phase * (areaH.value + 60f) - 40f
            val w = (8 + (i % 3) * 3).dp
            val h = (10 + (i % 2) * 6).dp
            Box(
                Modifier.offset(x = x.dp, y = y.dp).size(w, h)
                    .rotate(phase * 420f)
                    .alpha(((1f - phase) * 1.2f).coerceIn(0f, 1f))
                    .clip(RoundedCornerShape(3.dp))
                    .background(colors[i % 4])
            )
        }
    }
}
