package com.example.ui.screens

import java.text.NumberFormat
import java.util.Locale
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.ui.viewmodel.*
import kotlinx.coroutines.delay

/* ============================================================
 *  CartMe · "Calm" 디자인 토큰  (쿨 그레이 뉴트럴 + 트러스트 블루)
 *  팔레트만 바꾸면 전체 화면 톤이 함께 바뀝니다.
 * ============================================================ */
private val Ink        = Color(0xFF161A1F)   // 본문/제목
private val Sub        = Color(0xFF5E6571)   // 보조 텍스트
private val Faint      = Color(0xFF9AA0AB)   // 캡션/비활성
private val Line       = Color(0xFFE4E7EC)   // 경계선
private val Bg         = Color(0xFFEEF0F3)   // 앱 배경
private val Surface    = Color(0xFFFFFFFF)   // 카드
private val SurfaceAlt = Color(0xFFF4F6F9)   // 보조 면
private val Point      = Color(0xFF2F6BD8)   // 포인트(트러스트 블루)
private val PointDeep  = Color(0xFF1E50AC)   // 진한 포인트(텍스트용)
private val PointSoft  = Color(0xFFEAF1FC)   // 옅은 포인트 배경
private val OnPoint    = Color(0xFFFFFFFF)   // 포인트 위 텍스트
private val Warn       = Color(0xFFE0A100)
private val Danger     = Color(0xFFE5484D)

private val RadiusSm = 10.dp
private val Radius   = 16.dp
private val RadiusLg = 22.dp

private fun won(n: Int): String = NumberFormat.getNumberInstance(Locale.KOREA).format(n)

/* ============================================================
 *  ENTRY — MainActivity 가 호출하는 진입점 (시그니처 유지)
 * ============================================================ */
@Composable
fun CartAppContent(viewModel: CartViewModel, innerPadding: PaddingValues) {
    val uiState by viewModel.uiState.collectAsState()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Bg)
            .padding(innerPadding)
    ) {
        Crossfade(targetState = uiState.currentScreen, label = "screen") { screen ->
            when (screen) {
                Screen.SPLASH -> SplashScreen { viewModel.navigateTo(Screen.LOGIN) }
                Screen.LOGIN -> LoginScreen(
                    onLogin = { id, pw -> viewModel.login(id, pw) },
                    onSignUp = { viewModel.navigateTo(Screen.SIGNUP) }
                )
                Screen.SIGNUP -> SignUpScreen(
                    onSubmit = { n, p, i, w -> viewModel.signUp(n, p, i, w) },
                    onBack = { viewModel.navigateTo(Screen.LOGIN) }
                )
                Screen.DASHBOARD -> PairScreen(
                    uiState = uiState,
                    onPair = { viewModel.matchCart("CartMe-ROS2-08") },
                    onLogout = { viewModel.logout() }
                )
                Screen.SHOPPING -> ShoppingScreen(
                    uiState = uiState,
                    viewModel = viewModel,
                    onCheckout = { viewModel.navigateTo(Screen.PAYMENT) }
                )
                Screen.PAYMENT -> PaymentScreen(
                    uiState = uiState,
                    viewModel = viewModel,
                    onPay = { viewModel.navigateTo(Screen.COMPLETION) },
                    onBack = { viewModel.navigateTo(Screen.SHOPPING) }
                )
                Screen.COMPLETION -> CompletionScreen(
                    uiState = uiState,
                    viewModel = viewModel,
                    onRestart = { viewModel.logout() }
                )
            }
        }

        // 음성 안내 토스트
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
 *  공용 컴포넌트
 * ============================================================ */

// 브랜드 마크: "나(점)"를 카트가 따라오는 모양
@Composable
private fun BrandMark(size: Int = 56) {
    Canvas(modifier = Modifier.size(size.dp)) {
        val s = this.size.minDimension
        drawRoundRect(
            color = Point,
            size = Size(s, s),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(s * 0.28f, s * 0.28f)
        )
        drawCircle(color = OnPoint, radius = s * 0.115f, center = Offset(s * 0.37f, s * 0.5f))
        drawArc(
            color = OnPoint.copy(alpha = 0.55f), startAngle = -55f, sweepAngle = 110f, useCenter = false,
            topLeft = Offset(s * 0.40f, s * 0.30f), size = Size(s * 0.30f, s * 0.40f),
            style = Stroke(width = s * 0.06f)
        )
        drawArc(
            color = OnPoint.copy(alpha = 0.28f), startAngle = -58f, sweepAngle = 116f, useCenter = false,
            topLeft = Offset(s * 0.50f, s * 0.20f), size = Size(s * 0.40f, s * 0.60f),
            style = Stroke(width = s * 0.06f)
        )
    }
}

@Composable
private fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    leadingIcon: ImageVector? = null,
    outline: Boolean = false,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.fillMaxWidth().height(54.dp),
        shape = RoundedCornerShape(Radius),
        elevation = null,
        border = if (outline) androidx.compose.foundation.BorderStroke(1.5.dp, Line) else null,
        colors = ButtonDefaults.buttonColors(
            containerColor = if (outline) Surface else Point,
            contentColor = if (outline) Ink else OnPoint,
            disabledContainerColor = Line,
            disabledContentColor = Faint
        )
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun AppField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    leading: ImageVector,
    password: Boolean = false,
    keyboardType: KeyboardType = KeyboardType.Text,
    testTag: String = "",
) {
    Column {
        Text(label, fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = Sub)
        Spacer(Modifier.height(7.dp))
        OutlinedTextField(
            value = value,
            onValueChange = onValueChange,
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            shape = RoundedCornerShape(RadiusSm),
            leadingIcon = { Icon(leading, contentDescription = null, modifier = Modifier.size(20.dp)) },
            visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
            keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Point,
                unfocusedBorderColor = Line,
                focusedLeadingIconColor = Point,
                unfocusedLeadingIconColor = Faint,
                focusedContainerColor = Surface,
                unfocusedContainerColor = Surface,
            )
        )
    }
}

@Composable
private fun SectionHeader(title: String, trailing: @Composable (() -> Unit)? = null) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.3).sp)
        trailing?.invoke()
    }
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
            drawCircle(color = color.copy(alpha = (1.6f - a / 2.6f).coerceIn(0f, 1f) * 0.6f), radius = this.size.minDimension / 2 * a)
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
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(Radius))
                .background(Ink)
                .padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier.size(30.dp).clip(RoundedCornerShape(9.dp)).background(Point),
                contentAlignment = Alignment.Center
            ) { Icon(Icons.Filled.VolumeUp, contentDescription = null, tint = OnPoint, modifier = Modifier.size(17.dp)) }
            Spacer(Modifier.width(11.dp))
            Text(message, color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Medium, lineHeight = 18.sp)
        }
    }
}

/* ============================================================
 *  SPLASH
 * ============================================================ */
@Composable
private fun SplashScreen(onDone: () -> Unit) {
    var shown by remember { mutableStateOf(false) }
    val s by animateFloatAsState(if (shown) 1f else 0.84f, spring(0.6f, Spring.StiffnessLow), label = "s")
    LaunchedEffect(Unit) { shown = true; delay(1800); onDone() }
    Box(Modifier.fillMaxSize().background(Bg), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.scale(s)) { BrandMark(84) }
            Spacer(Modifier.height(22.dp))
            Text("CartMe", fontSize = 30.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.6).sp)
            Spacer(Modifier.height(6.dp))
            Text("나를 따라오는 스마트 쇼핑카트", fontSize = 13.5.sp, fontWeight = FontWeight.Medium, color = Sub)
        }
    }
}

/* ============================================================
 *  LOGIN
 * ============================================================ */
@Composable
private fun LoginScreen(onLogin: (String, String) -> Boolean, onSignUp: () -> Unit) {
    var id by remember { mutableStateOf("user123") }
    var pw by remember { mutableStateOf("password") }
    var error by remember { mutableStateOf(false) }
    val focus = LocalFocusManager.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp)
    ) {
        Spacer(Modifier.height(36.dp))
        BrandMark(48)
        Spacer(Modifier.height(22.dp))
        Text("다시 만나서\n반가워요", fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, color = Ink, lineHeight = 32.sp, letterSpacing = (-0.6).sp)
        Spacer(Modifier.height(10.dp))
        Text("카트미 계정으로 로그인하세요", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Sub)
        Spacer(Modifier.height(28.dp))

        AppField("아이디", id, { id = it; error = false }, Icons.Filled.AccountCircle)
        Spacer(Modifier.height(14.dp))
        AppField("비밀번호", pw, { pw = it; error = false }, Icons.Filled.Lock, password = true)

        if (error) {
            Spacer(Modifier.height(8.dp))
            Text("아이디 또는 비밀번호를 확인해 주세요.", color = Danger, fontSize = 12.sp)
        }

        Spacer(Modifier.height(26.dp))
        PrimaryButton("로그인", { focus.clearFocus(); if (!onLogin(id, pw)) error = true })

        Spacer(Modifier.height(18.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Center) {
            Text("처음이신가요? ", fontSize = 13.5.sp, color = Sub, fontWeight = FontWeight.Medium)
            Text("회원가입", fontSize = 13.5.sp, color = PointDeep, fontWeight = FontWeight.Bold,
                modifier = Modifier.clickable { onSignUp() })
        }
        Spacer(Modifier.height(24.dp))
    }
}

/* ============================================================
 *  SIGN-UP
 * ============================================================ */
@Composable
private fun SignUpScreen(onSubmit: (String, String, String, String) -> Boolean, onBack: () -> Unit) {
    var name by remember { mutableStateOf("홍길동") }
    var phone by remember { mutableStateOf("010-1234-5678") }
    var id by remember { mutableStateOf("user123") }
    var pw by remember { mutableStateOf("password") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp)
    ) {
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.clickable { onBack() }.padding(vertical = 8.dp)) {
            Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Sub, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(4.dp))
            Text("로그인", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Sub)
        }
        Spacer(Modifier.height(14.dp))
        Text("회원가입", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.6).sp)
        Spacer(Modifier.height(6.dp))
        Text("맞춤 자동 추종을 위해 등록해 주세요", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Sub)
        Spacer(Modifier.height(24.dp))

        AppField("이름", name, { name = it }, Icons.Filled.Person)
        Spacer(Modifier.height(13.dp))
        AppField("휴대폰 번호", phone, { phone = it }, Icons.Filled.Phone, keyboardType = KeyboardType.Phone)
        Spacer(Modifier.height(13.dp))
        AppField("아이디", id, { id = it }, Icons.Filled.AccountCircle)
        Spacer(Modifier.height(13.dp))
        AppField("비밀번호", pw, { pw = it }, Icons.Filled.Lock, password = true)

        Spacer(Modifier.height(24.dp))
        PrimaryButton("가입하고 시작하기", { onSubmit(name, phone, id, pw) })
        Spacer(Modifier.height(24.dp))
    }
}

/* ============================================================
 *  PAIR (대시보드 / QR 매칭)
 * ============================================================ */
@Composable
private fun PairScreen(uiState: CartUiState, onPair: () -> Unit, onLogout: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 20.dp)
    ) {
        Spacer(Modifier.height(10.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text("이마트 성수점", fontSize = 12.5.sp, fontWeight = FontWeight.SemiBold, color = Sub)
                Text("${uiState.userName} 님, 안녕하세요", fontSize = 19.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.4).sp)
            }
            IconChipButton(Icons.Filled.ExitToApp, onLogout)
        }

        Spacer(Modifier.height(20.dp))
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(RadiusLg))
                .background(Surface)
                .padding(vertical = 26.dp, horizontal = 22.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                modifier = Modifier.clip(CircleShape).background(PointSoft).padding(horizontal = 12.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(Modifier.size(6.dp).clip(CircleShape).background(Point))
                Spacer(Modifier.width(6.dp))
                Text("주변 카트 1대 발견", fontSize = 11.5.sp, fontWeight = FontWeight.Bold, color = PointDeep)
            }
            Spacer(Modifier.height(16.dp))
            Text("카트와 연결하기", fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.5).sp)
            Spacer(Modifier.height(4.dp))
            Text("카트 화면의 카메라에 QR 코드를\n가까이 비춰 주세요", fontSize = 13.sp, color = Sub, textAlign = TextAlign.Center, lineHeight = 19.sp)
            Spacer(Modifier.height(20.dp))
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(Radius))
                    .background(Surface)
                    .border(1.dp, Line, RoundedCornerShape(Radius))
                    .padding(16.dp)
            ) { FauxQr() }

            if (uiState.qrToken.isNotBlank()) {
                Spacer(Modifier.height(12.dp))
                
                // 3분(180초) 타이머 상태 관리 및 LaunchedEffect 구현
                var timeLeft by remember(uiState.qrToken) { mutableStateOf(180) }
                LaunchedEffect(uiState.qrToken) {
                    timeLeft = 180
                    while (timeLeft > 0) {
                        delay(1000L)
                        timeLeft--
                    }
                }
                
                val minutes = timeLeft / 60
                val seconds = timeLeft % 60
                val timeString = "%02d:%02d".format(minutes, seconds)
                val isTimeExpired = timeLeft == 0

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.Center
                ) {
                    Icon(
                        imageVector = Icons.Filled.Timer,
                        contentDescription = "Timer",
                        tint = if (isTimeExpired) Danger else Point,
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        text = if (isTimeExpired) "시간 만료 (재발급 필요)" else "남은 시간: $timeString",
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        color = if (isTimeExpired) Danger else Point
                    )
                }

                Spacer(Modifier.height(8.dp))
                Text("3분 내에 스캔해 주세요 · 스캔 시 자동 이동",
                    fontSize = 11.sp, color = Faint, textAlign = TextAlign.Center)
            }
        }

        Spacer(Modifier.height(14.dp))
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(Radius))
                .background(PointSoft)
                .padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(Icons.Filled.Shield, contentDescription = null, tint = PointDeep, modifier = Modifier.size(26.dp))
            Spacer(Modifier.width(12.dp))
            Column {
                Text("교통약자 안심 주행", fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Ink)
                Text("LiDAR·초음파 센서로 충돌을 방지해요", fontSize = 11.5.sp, color = Sub)
            }
        }

        Spacer(Modifier.weight(1f))
        PrimaryButton("QR 인식 · 카트 연결", onPair, leadingIcon = Icons.Filled.QrCodeScanner)
        Spacer(Modifier.height(20.dp))
    }
}

@Composable
private fun IconChipButton(icon: ImageVector, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(40.dp)
            .clip(RoundedCornerShape(12.dp))
            .background(Surface)
            .border(1.dp, Line, RoundedCornerShape(12.dp))
            .clickable { onClick() },
        contentAlignment = Alignment.Center
    ) { Icon(icon, contentDescription = null, tint = Sub, modifier = Modifier.size(19.dp)) }
}

@Composable
private fun FauxQr() {
    Canvas(Modifier.size(180.dp)) {
        val n = 13
        val cell = this.size.width / (n + 1)
        val pad = cell / 2
        var seed = 7
        fun rnd(): Float { seed = (seed * 9301 + 49297) % 233280; return seed / 233280f }
        for (y in 0 until n) for (x in 0 until n) {
            val corner = (x < 3 && y < 3) || (x > n - 4 && y < 3) || (x < 3 && y > n - 4)
            if (corner) continue
            if (rnd() > 0.52f) {
                drawRoundRect(
                    color = Ink,
                    topLeft = Offset(pad + x * cell, pad + y * cell),
                    size = Size(cell * 0.78f, cell * 0.78f),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(cell * 0.2f, cell * 0.2f)
                )
            }
        }
        // 3 finder eyes
        fun eye(cx: Float, cy: Float) {
            drawRoundRect(color = Ink, topLeft = Offset(cx, cy), size = Size(cell * 3f, cell * 3f),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(cell, cell), style = Stroke(width = cell * 0.5f))
            drawRoundRect(color = Point, topLeft = Offset(cx + cell, cy + cell), size = Size(cell, cell),
                cornerRadius = androidx.compose.ui.geometry.CornerRadius(cell * 0.4f, cell * 0.4f))
        }
        eye(pad, pad)
        eye(pad + (n - 3) * cell, pad)
        eye(pad, pad + (n - 3) * cell)
    }
}

/* ============================================================
 *  SHOPPING (핵심 화면)
 * ============================================================ */
@Composable
private fun ShoppingScreen(uiState: CartUiState, viewModel: CartViewModel, onCheckout: () -> Unit) {
    var showSheet by remember { mutableStateOf(false) }
    val count = uiState.shoppingList.sumOf { it.quantity }
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            // top bar
            Row(
                modifier = Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, top = 10.dp, bottom = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text("이마트 성수점 · 쇼핑 중", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Sub)
                    Text("나의 카트", fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.6).sp)
                }
                IconChipButton(Icons.Filled.ExitToApp) { viewModel.logout() }
            }

            // scroll area
            Column(
                modifier = Modifier
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp)
            ) {
                StatusCard(uiState, onSet = { viewModel.setTrackingState(it) }, onReturn = { viewModel.completeOrder() })
                Spacer(Modifier.height(20.dp))
                SectionHeader("담은 상품 $count") {
                    Row(
                        modifier = Modifier.clip(CircleShape).background(PointSoft)
                            .clickable { showSheet = true }.padding(horizontal = 12.dp, vertical = 7.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Filled.Add, contentDescription = null, tint = PointDeep, modifier = Modifier.size(15.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("상품 담기", fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = PointDeep)
                    }
                }
                Spacer(Modifier.height(12.dp))

                if (uiState.shoppingList.isEmpty()) {
                    EmptyCart()
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                        uiState.shoppingList.forEach { item ->
                            ItemRow(item) { viewModel.removeItem(item) }
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))
            }

            // sticky checkout
            Box(Modifier.fillMaxWidth().height(1.dp).background(Line))
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .background(Surface)
                    .padding(horizontal = 20.dp, vertical = 14.dp)
            ) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
                    Text("예상 결제 금액", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Sub)
                    Row(verticalAlignment = Alignment.Bottom) {
                        Text(won(total), fontSize = 22.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.5).sp)
                        Text("원", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Ink, modifier = Modifier.padding(start = 2.dp, bottom = 1.dp))
                    }
                }
                Spacer(Modifier.height(10.dp))
                PrimaryButton("결제하기", onCheckout, enabled = uiState.shoppingList.isNotEmpty())
            }
        }

        // add-product bottom sheet
        AddProductSheet(visible = showSheet, onAdd = { n, p, e -> viewModel.simulateRfidScan(n, p, e) }, onClose = { showSheet = false })
    }
}

@Composable
private fun StatusCard(uiState: CartUiState, onSet: (TrackingState) -> Unit, onReturn: () -> Unit) {
    val following = uiState.trackingState == TrackingState.FOLLOWING
    val tone: Color; val toneInk: Color; val toneBg: Color; val icon: ImageVector; val label: String; val desc: String
    when (uiState.trackingState) {
        TrackingState.FOLLOWING -> { tone = Point; toneInk = PointDeep; toneBg = PointSoft; icon = Icons.Filled.NearMe; label = "자동 추종 중"; desc = "안전하게 따라가요" }
        TrackingState.PAUSED -> { tone = Faint; toneInk = Sub; toneBg = SurfaceAlt; icon = Icons.Filled.Pause; label = "일시 정지"; desc = "다시 시작하면 추종해요" }
        TrackingState.LOST_TRACKING -> { tone = Warn; toneInk = Color(0xFF946800); toneBg = Color(0x1FE0A100); icon = Icons.Filled.Shield; label = "사용자 인식 실패"; desc = "카트 정면 카메라 앞에 서주세요" }
        TrackingState.DISCONNECTED -> { tone = Danger; toneInk = Color(0xFFB4242A); toneBg = Color(0x1AE5484D); icon = Icons.Filled.Shield; label = "통신 지연"; desc = "Wi-Fi 연결 상태를 확인해 주세요" }
    }

    Column(
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RadiusLg)).background(Surface).padding(16.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                PulsingDot(tone)
                Spacer(Modifier.width(4.dp))
                Text(uiState.matchedCartId.substringAfter("ROS2-").let { "CartMe-$it" }, fontSize = 14.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.BatteryFull, contentDescription = null, tint = if (uiState.cartBattery > 20) Sub else Danger, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(5.dp))
                Text("${uiState.cartBattery}%", fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = if (uiState.cartBattery > 20) Sub else Danger)
            }
        }

        Spacer(Modifier.height(13.dp))
        Row(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(RadiusSm)).background(toneBg).padding(horizontal = 14.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(icon, contentDescription = null, tint = tone, modifier = Modifier.size(22.dp))
            Spacer(Modifier.width(11.dp))
            Column {
                Text(label, fontSize = 13.5.sp, fontWeight = FontWeight.ExtraBold, color = toneInk)
                Text(desc, fontSize = 11.5.sp, fontWeight = FontWeight.Medium, color = Sub)
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (following) {
                PrimaryButton(
                    text = "정지",
                    onClick = { onSet(TrackingState.PAUSED) },
                    leadingIcon = Icons.Filled.Pause,
                    outline = true,
                    modifier = Modifier.weight(1f)
                )
            } else {
                PrimaryButton(
                    text = "추종 시작",
                    onClick = { onSet(TrackingState.FOLLOWING) },
                    leadingIcon = Icons.Filled.PlayArrow,
                    modifier = Modifier.weight(1f)
                )
            }
            PrimaryButton(
                text = "복귀",
                onClick = onReturn,
                leadingIcon = Icons.Filled.Home,
                outline = true,
                modifier = Modifier.weight(1f)
            )
        }
    }
}

@Composable
private fun SegButton(text: String, icon: ImageVector, active: Boolean, activeBg: Color, activeFg: Color, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(
        modifier = modifier
            .height(42.dp)
            .clip(RoundedCornerShape(RadiusSm - 1.dp))
            .background(if (active) activeBg else Color.Transparent)
            .clickable { onClick() },
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, contentDescription = null, tint = if (active) activeFg else Sub, modifier = Modifier.size(16.dp))
        Spacer(Modifier.width(6.dp))
        Text(text, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = if (active) activeFg else Sub)
    }
}

@Composable
private fun ItemRow(item: CartItem, onRemove: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius)).background(Surface).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(44.dp).clip(RoundedCornerShape(RadiusSm)).background(SurfaceAlt), contentAlignment = Alignment.Center) {
            Text(item.imageEmoji, fontSize = 22.sp)
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(item.name, fontSize = 14.5.sp, fontWeight = FontWeight.Bold, color = Ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text("${item.id} · ${item.quantity}개", fontSize = 11.5.sp, fontWeight = FontWeight.Medium, color = Faint)
        }
        Spacer(Modifier.width(8.dp))
        Text("${won(item.price * item.quantity)}원", fontSize = 14.5.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
        Box(Modifier.size(34.dp).clip(RoundedCornerShape(9.dp)).clickable { onRemove() }, contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.DeleteOutline, contentDescription = "삭제", tint = Faint, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
private fun EmptyCart() {
    Column(
        modifier = Modifier.fillMaxWidth().padding(vertical = 40.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Icon(Icons.Filled.ShoppingCart, contentDescription = null, tint = Faint, modifier = Modifier.size(40.dp))
        Spacer(Modifier.height(10.dp))
        Text("카트가 비어있어요", fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, color = Sub)
        Text("상품을 담으면 RFID가 자동 인식해요", fontSize = 12.sp, color = Faint)
    }
}

private data class CatalogItem(val name: String, val price: Int, val emoji: String)
private val CATALOG = listOf(
    CatalogItem("제주 삼다수 2L", 1200, "💧"),
    CatalogItem("신라면 5봉", 4380, "🍜"),
    CatalogItem("한우 등심 300g", 34500, "🥩"),
    CatalogItem("유기농 바나나", 3900, "🍌"),
    CatalogItem("서울우유 1L", 2980, "🥛"),
    CatalogItem("대파 한 단", 2490, "🥬"),
)

@Composable
private fun BoxScope.AddProductSheet(visible: Boolean, onAdd: (String, Int, String) -> Unit, onClose: () -> Unit) {
    // scrim
    AnimatedVisibility(visible, enter = fadeIn(), exit = fadeOut(), modifier = Modifier.matchParentSize()) {
        Box(Modifier.fillMaxSize().background(Color(0x57000000)).clickable(onClick = onClose))
    }
    AnimatedVisibility(
        visible,
        enter = slideInVertically { it } + fadeIn(),
        exit = slideOutVertically { it } + fadeOut(),
        modifier = Modifier.align(Alignment.BottomCenter)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth()
                .clip(RoundedCornerShape(topStart = RadiusLg, topEnd = RadiusLg))
                .background(Surface)
                .padding(start = 18.dp, end = 18.dp, top = 10.dp, bottom = 22.dp)
        ) {
            Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                Box(Modifier.width(40.dp).height(4.5.dp).clip(CircleShape).background(Line))
            }
            Spacer(Modifier.height(16.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.NearMe, contentDescription = null, tint = PointDeep, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text("상품 담기", fontSize = 16.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
            }
            Spacer(Modifier.height(4.dp))
            Text("카트에 담으면 RFID가 자동으로 인식해요", fontSize = 12.sp, color = Sub)
            Spacer(Modifier.height(14.dp))
            CATALOG.chunked(2).forEach { row ->
                Row(Modifier.fillMaxWidth().padding(bottom = 9.dp), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                    row.forEach { c ->
                        Row(
                            modifier = Modifier.weight(1f).clip(RoundedCornerShape(RadiusSm)).background(SurfaceAlt)
                                .clickable { onAdd(c.name, c.price, c.emoji) }.padding(horizontal = 12.dp, vertical = 11.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(c.emoji, fontSize = 19.sp)
                            Spacer(Modifier.width(9.dp))
                            Column(Modifier.weight(1f)) {
                                Text(c.name, fontSize = 12.5.sp, fontWeight = FontWeight.Bold, color = Ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text("${won(c.price)}원", fontSize = 11.sp, fontWeight = FontWeight.SemiBold, color = Sub)
                            }
                            Icon(Icons.Filled.Add, contentDescription = null, tint = PointDeep, modifier = Modifier.size(16.dp))
                        }
                    }
                    if (row.size == 1) Spacer(Modifier.weight(1f))
                }
            }
        }
    }
}

/* ============================================================
 *  PAYMENT
 * ============================================================ */
@Composable
private fun PaymentScreen(uiState: CartUiState, viewModel: CartViewModel, onPay: () -> Unit, onBack: () -> Unit) {
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }
    Column(Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp, end = 20.dp, top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(40.dp).clip(RoundedCornerShape(12.dp)).clickable { onBack() }, contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.ArrowBack, contentDescription = "뒤로", tint = Ink, modifier = Modifier.size(22.dp))
            }
            Spacer(Modifier.width(6.dp))
            Text("결제 명세서", fontSize = 19.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.4).sp)
        }

        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(RadiusLg)).background(Surface).padding(18.dp)) {
                uiState.shoppingList.forEach { item ->
                    Row(Modifier.fillMaxWidth().padding(bottom = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(item.imageEmoji, fontSize = 20.sp)
                        Spacer(Modifier.width(11.dp))
                        Column(Modifier.weight(1f)) {
                            Text(item.name, fontSize = 14.sp, fontWeight = FontWeight.Bold, color = Ink)
                            Text("${won(item.price)}원 · ${item.quantity}개", fontSize = 11.5.sp, fontWeight = FontWeight.Medium, color = Sub)
                        }
                        Text("${won(item.price * item.quantity)}원", fontSize = 14.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
                    }
                }
                Divider(color = Line, modifier = Modifier.padding(vertical = 4.dp))
                Spacer(Modifier.height(14.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
                    Text("총 결제금액", fontSize = 15.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
                    Text("${won(total)}원", fontSize = 22.sp, fontWeight = FontWeight.ExtraBold, color = PointDeep, letterSpacing = (-0.5).sp)
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius)).background(SurfaceAlt).padding(horizontal = 16.dp, vertical = 13.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Filled.Shield, contentDescription = null, tint = PointDeep, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(10.dp))
                Text("앱 간편결제로 안전하게 결제돼요", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Sub)
            }
        }

        Column(Modifier.padding(horizontal = 20.dp, vertical = 14.dp)) {
            PrimaryButton("${won(total)}원 간편결제", onPay)
        }
    }
}

/* ============================================================
 *  COMPLETION
 * ============================================================ */
@Composable
private fun CompletionScreen(uiState: CartUiState, viewModel: CartViewModel, onRestart: () -> Unit) {
    val total = uiState.shoppingList.sumOf { it.price * it.quantity }
    val count = uiState.shoppingList.sumOf { it.quantity }

    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 28.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Box(Modifier.size(96.dp).clip(CircleShape).background(Point), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Check, contentDescription = null, tint = OnPoint, modifier = Modifier.size(48.dp))
        }
        Spacer(Modifier.height(20.dp))
        Text("결제 완료", fontSize = 25.sp, fontWeight = FontWeight.ExtraBold, color = Ink, letterSpacing = (-0.6).sp)
        Spacer(Modifier.height(8.dp))
        Text("이용해 주셔서 감사합니다.\n카트가 충전 구역으로 복귀하고 있어요", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = Sub, textAlign = TextAlign.Center, lineHeight = 21.sp)

        Spacer(Modifier.height(26.dp))
        Row(
            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius)).background(Surface).padding(horizontal = 18.dp, vertical = 16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text("결제 금액", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = Sub)
                Text("${won(total)}원", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
            }
            Box(Modifier.width(1.dp).height(40.dp).background(Line))
            Column {
                Text("구매 상품", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = Sub)
                Text("${count}개", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
            }
        }

        Spacer(Modifier.height(18.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(6.dp).clip(CircleShape).background(Point))
            Spacer(Modifier.width(8.dp))
            Text("${uiState.matchedCartId} 충전 구역으로 복귀 중", fontSize = 11.5.sp, fontWeight = FontWeight.SemiBold, color = Faint)
        }

        Spacer(Modifier.height(28.dp))
        PrimaryButton("처음으로", onRestart, outline = true, leadingIcon = Icons.Filled.Home)
    }
}
