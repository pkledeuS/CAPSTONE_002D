
$(document).ready(function(){
    $('.carousel-2 .product-item:gt(6)').remove();
    $('.carousel-2').slick({
        slidesToShow: 3,
        slidesToScroll: 1,
        dots: true,
        centerMode: true,
        centerPadding: '0px',
        focusOnSelect: true,
        autoplay: true,
        autoplaySpeed: 4000,
    });
});